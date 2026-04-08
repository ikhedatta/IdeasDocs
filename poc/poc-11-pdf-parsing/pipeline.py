"""Pipeline orchestrator — end-to-end PDF → structured chunks.

Coordinates all 5 phases:
  0. Classify PDF type
  1. Extract text (pdfplumber + PyMuPDF) with garble detection
  1b. OCR fallback for garbled regions
  2. Layout analysis (region classification)
  3. Reading order (column detection + sort)
  4. Chunking (semantic + token-bounded)
  5. Embedding (optional hook)

Supports page-level parallelism via ThreadPoolExecutor.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from timeit import default_timer as timer
from typing import Optional

from PIL import Image

from chunker import chunk_text_boxes
from classifier import classify_document
from config import MAX_PAGES_PARALLEL
from embeddings import BaseEmbedder, NoOpEmbedder
from layout_analyzer import BaseLayoutAnalyzer, HeuristicLayoutAnalyzer
from models import Chunk, DocumentResult, GarbleStrategy, LayoutType, PDFType, PageResult
from ocr_engine import BaseOCREngine, NoOpOCREngine, TesseractOCREngine
from reading_order import (
    assign_columns,
    detect_columns,
    merge_adjacent_boxes,
    sort_reading_order,
)
from text_extractor import TextExtractor

logger = logging.getLogger(__name__)


# ── Stage Reporter ─────────────────────────────────────────────────────

def _header(title: str, width: int = 80) -> str:
    return f"\n{'═' * width}\n  {title}\n{'═' * width}"


def _subheader(title: str, width: int = 80) -> str:
    return f"\n{'─' * width}\n  {title}\n{'─' * width}"


def print_stage_extraction(page_result: PageResult, page_num: int) -> None:
    """Print Phase 1 extraction results for a page."""
    boxes = page_result.text_boxes
    garble_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for b in boxes:
        garble_counts[b.garble_strategy.value] = garble_counts.get(b.garble_strategy.value, 0) + 1
        source_counts[b.source] = source_counts.get(b.source, 0) + 1

    print(f"  Page {page_num}: {len(boxes)} text boxes extracted")
    print(f"    Sources     : {source_counts}")
    print(f"    Garble flags: {garble_counts}")
    if boxes:
        fonts = set()
        for b in boxes:
            if b.font_name:
                fonts.add(b.font_name)
        if fonts:
            shown = sorted(fonts)[:8]
            extra = f" (+{len(fonts) - 8} more)" if len(fonts) > 8 else ""
            print(f"    Fonts       : {', '.join(shown)}{extra}")
        sample = boxes[0]
        preview = sample.text[:80].replace("\n", "\\n")
        print(f"    First box   : \"{preview}{'…' if len(sample.text) > 80 else ''}\"")


def print_stage_ocr(page_result: PageResult, page_num: int, ocr_count: int) -> None:
    """Print Phase 1b OCR results."""
    if ocr_count > 0:
        ocr_boxes = [b for b in page_result.text_boxes if b.source in ("ocr", "ocr_full")]
        print(f"  Page {page_num}: {ocr_count} boxes filled via OCR")
        for b in ocr_boxes[:3]:
            preview = b.text[:60].replace("\n", "\\n")
            print(f"    OCR result: \"{preview}{'…' if len(b.text) > 60 else ''}\"")
    else:
        print(f"  Page {page_num}: No OCR needed (text extraction sufficient)")


def print_stage_layout(page_result: PageResult, page_num: int) -> None:
    """Print Phase 2 layout analysis results."""
    layout_counts: dict[str, int] = {}
    for b in page_result.text_boxes:
        layout_counts[b.layout_type.value] = layout_counts.get(b.layout_type.value, 0) + 1
    print(f"  Page {page_num}: {layout_counts}")

    # Show titles / section headers detected
    titles = [b.text.strip() for b in page_result.text_boxes if b.layout_type == LayoutType.TITLE]
    if titles:
        print(f"    Section titles: {titles[:6]}")


def print_stage_reading_order(page_result: PageResult, page_num: int, num_cols: int) -> None:
    """Print Phase 3 reading order results."""
    print(f"  Page {page_num}: {num_cols} column(s) detected, {len(page_result.text_boxes)} boxes after merge")
    if page_result.text_boxes:
        order_preview = [b.text[:30].replace("\n", " ").strip() for b in page_result.text_boxes[:5]]
        print(f"    Reading order (first 5): {order_preview}")


def print_stage_chunks(chunks: list[Chunk]) -> None:
    """Print Phase 4 chunking results."""
    if not chunks:
        print("  No chunks produced.")
        return

    total_tokens = sum(c.token_count for c in chunks)
    avg_tokens = total_tokens // len(chunks) if chunks else 0
    print(f"  {len(chunks)} chunks | Total tokens: {total_tokens} | Avg: {avg_tokens} tokens/chunk")
    print()

    for i, chunk in enumerate(chunks):
        section = chunk.metadata.get("section_title", "")
        section_label = f" [{section}]" if section else ""
        pages = sorted(set(p["page"] for p in chunk.positions)) if chunk.positions else []
        page_label = f"pg {','.join(str(p) for p in pages)}" if pages else "?"

        print(f"  Chunk {i}{section_label} ({page_label}, {chunk.token_count} tokens):")
        # Show content preview: first 200 chars
        content = chunk.content[:200].replace("\n", "\\n")
        if len(chunk.content) > 200:
            content += "…"
        print(f"    \"{content}\"")
        print()


class PDFParsingPipeline:
    """End-to-end PDF parsing pipeline with pluggable components.

    Usage:
        pipeline = PDFParsingPipeline()
        result = pipeline.parse("resume.pdf")
        chunks = result["chunks"]
    """

    def __init__(
        self,
        ocr_engine: Optional[BaseOCREngine] = None,
        layout_analyzer: Optional[BaseLayoutAnalyzer] = None,
        embedder: Optional[BaseEmbedder] = None,
        max_workers: int = MAX_PAGES_PARALLEL,
        verbose: bool = False,
    ):
        self.text_extractor = TextExtractor()
        self.ocr_engine = ocr_engine or self._init_ocr()
        self.layout_analyzer = layout_analyzer or HeuristicLayoutAnalyzer()
        self.embedder = embedder  # None = skip embedding
        self.max_workers = max_workers
        self.verbose = verbose

    @staticmethod
    def _init_ocr() -> BaseOCREngine:
        """Initialize OCR engine, falling back to no-op if unavailable."""
        engine = TesseractOCREngine()
        if engine.available:
            return engine
        logger.warning("Tesseract not available — OCR disabled")
        return NoOpOCREngine()

    def parse(
        self,
        pdf_path: str,
        filename: str = "",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        skip_embedding: bool = False,
    ) -> dict:
        """Parse a PDF file end-to-end.

        Args:
            pdf_path: Path to the PDF file.
            filename: Display name for the document.
            chunk_size: Override chunk token size.
            chunk_overlap: Override chunk overlap tokens.
            skip_embedding: If True, skip the embedding phase.

        Returns:
            Dict with keys: document, chunks, raw_pages
        """
        overall_start = timer()
        if not filename:
            import os
            filename = os.path.basename(pdf_path)

        # ── Count pages ────────────────────────────────────────────
        import fitz
        doc = fitz.open(pdf_path)
        page_count = doc.page_count
        doc.close()

        logger.info("Parsing '%s' (%d pages)", filename, page_count)

        # ── Phase 0-1: Extract text from all pages (parallel) ─────
        page_results: list[tuple[PageResult, Optional[Image.Image]]] = [None] * page_count

        if page_count <= 2 or self.max_workers <= 1:
            # Sequential for small documents
            for pg in range(page_count):
                page_results[pg] = self._process_page(pdf_path, pg)
        else:
            # Parallel for larger documents
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(self._process_page, pdf_path, pg): pg
                    for pg in range(page_count)
                }
                for future in as_completed(futures):
                    pg = futures[future]
                    page_results[pg] = future.result()

        # ── Classify document type ─────────────────────────────────
        page_types = [pr.pdf_type for pr, _ in page_results]
        doc_type = classify_document(page_types)
        logger.info("Document classified as: %s", doc_type.value)

        if self.verbose:
            print(_header(f"DOCUMENT CLASSIFICATION — {filename}"))
            print(f"  PDF type : {doc_type.value}")
            print(f"  Pages    : {page_count}")
            for i, pt in enumerate(page_types):
                print(f"    Page {i}: {pt.value}")

        # ── Collect all text boxes across pages ────────────────────
        all_boxes = []
        total_garbled = 0
        total_ocr = 0
        pages: list[PageResult] = []

        for page_result, page_image in page_results:
            pages.append(page_result)
            total_garbled += page_result.garbled_box_count
            total_ocr += page_result.ocr_box_count
            all_boxes.extend(page_result.text_boxes)

        if self.verbose:
            print(f"\n  Total text boxes: {len(all_boxes)}")
            print(f"  Garbled boxes   : {total_garbled}")
            print(f"  OCR-filled boxes: {total_ocr}")

            # Print full extracted text per page
            print(_header("EXTRACTED TEXT"))
            for page_result in pages:
                print(_subheader(f"Page {page_result.page_number}"))
                page_text = " ".join(
                    b.text for b in page_result.text_boxes if b.text.strip()
                )
                if page_text:
                    print(page_text)
                else:
                    print("  (no text extracted)")
                print()

        # ── Phase 4: Chunking ─────────────────────────────────────
        doc_id = DocumentResult(
            filename=filename,
            page_count=page_count,
            pdf_type=doc_type,
        ).id

        chunk_start = timer()
        chunks = chunk_text_boxes(
            all_boxes,
            document_id=doc_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunk_ms = (timer() - chunk_start) * 1000

        if self.verbose:
            print(_header("PHASE 4 — CHUNKING"))
            print(f"  Chunk size: {chunk_size or 'default'} tokens | Overlap: {chunk_overlap or 'default'} tokens")
            print(f"  Time: {chunk_ms:.1f}ms")
            print_stage_chunks(chunks)

        # ── Phase 5: Embedding (optional) ──────────────────────────
        if not skip_embedding and self.embedder is not None:
            embed_start = timer()
            chunks = self.embedder.embed_chunks(chunks)
            embed_ms = (timer() - embed_start) * 1000
            logger.info("Embedding took %.1fms", embed_ms)
            if self.verbose:
                print(_header("PHASE 5 — EMBEDDING"))
                dim = chunks[0].embedding and len(chunks[0].embedding) or 0
                print(f"  Embedded {len(chunks)} chunks (dim={dim}) in {embed_ms:.1f}ms")
        elif self.verbose:
            print(_header("PHASE 5 — EMBEDDING (skipped)"))

        # ── Build result ───────────────────────────────────────────
        elapsed_ms = (timer() - overall_start) * 1000

        document = DocumentResult(
            id=doc_id,
            filename=filename,
            page_count=page_count,
            pdf_type=doc_type,
            pages=pages,
            processing_time_ms=elapsed_ms,
            total_text_boxes=len(all_boxes),
            total_garbled_boxes=total_garbled,
            total_ocr_boxes=total_ocr,
        )

        logger.info(
            "Parsed '%s': %d pages, %d boxes (%d garbled, %d OCR), %d chunks in %.0fms",
            filename, page_count, len(all_boxes),
            total_garbled, total_ocr, len(chunks), elapsed_ms,
        )

        if self.verbose:
            print(_header("PIPELINE SUMMARY"))
            print(f"  File       : {filename}")
            print(f"  PDF type   : {doc_type.value}")
            print(f"  Pages      : {page_count}")
            print(f"  Text boxes : {len(all_boxes)} ({total_garbled} garbled → {total_ocr} OCR-filled)")
            print(f"  Chunks     : {len(chunks)}")
            print(f"  Total time : {elapsed_ms:.0f}ms")
            print(f"{'═' * 80}")

        return {
            "document": document,
            "chunks": chunks,
            "raw_pages": pages,
        }

    def _process_page(
        self,
        pdf_path: str,
        page_number: int,
    ) -> tuple[PageResult, Optional[Image.Image]]:
        """Process a single page through Phases 1-3.

        Returns:
            (PageResult, page_image)
        """
        if self.verbose and page_number == 0:
            print(_header("PHASE 1 — TEXT EXTRACTION + GARBLE DETECTION"))

        # Phase 1: Text extraction with garble detection
        extract_start = timer()
        page_result, page_image = self.text_extractor.extract_page(
            pdf_path, page_number
        )
        extract_ms = (timer() - extract_start) * 1000

        if self.verbose:
            print(f"\n  [Phase 1] Page {page_number} — Text extraction ({extract_ms:.0f}ms)")
            print_stage_extraction(page_result, page_number)

        # Phase 1b: OCR fallback for garbled boxes
        ocr_count = 0
        if page_image is not None:
            ocr_start = timer()
            page_result.text_boxes, ocr_count = self.ocr_engine.fill_garbled_boxes(
                page_result.text_boxes, page_image
            )
            page_result.ocr_box_count = ocr_count
            ocr_ms = (timer() - ocr_start) * 1000

            if self.verbose:
                print(f"\n  [Phase 1b] Page {page_number} — OCR fallback ({ocr_ms:.0f}ms)")
                print_stage_ocr(page_result, page_number, ocr_count)

        # Phase 2: Layout analysis
        layout_start = timer()
        page_result.text_boxes = self.layout_analyzer.analyze(
            page_result.text_boxes,
            page_result.width,
            page_result.height,
        )
        layout_ms = (timer() - layout_start) * 1000

        if self.verbose:
            print(f"\n  [Phase 2] Page {page_number} — Layout analysis ({layout_ms:.0f}ms)")
            print_stage_layout(page_result, page_number)

        # Phase 3: Reading order
        order_start = timer()
        num_cols = detect_columns(
            page_result.text_boxes,
            page_result.width,
        )
        page_result.text_boxes = assign_columns(
            page_result.text_boxes,
            page_result.width,
            num_cols,
        )
        page_result.text_boxes = sort_reading_order(page_result.text_boxes)
        page_result.text_boxes = merge_adjacent_boxes(page_result.text_boxes)
        order_ms = (timer() - order_start) * 1000

        if self.verbose:
            print(f"\n  [Phase 3] Page {page_number} — Reading order ({order_ms:.0f}ms)")
            print_stage_reading_order(page_result, page_number, num_cols)

        return page_result, page_image


# ── CLI Runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.WARNING,
        format="%(name)s %(levelname)s %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_path> [chunk_size]")
        print("  Runs the full pipeline with verbose stage output.")
        print("  No external dependencies (no database, no API server).")
        sys.exit(1)

    pdf_file = sys.argv[1]
    c_size = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if not os.path.isfile(pdf_file):
        print(f"Error: File not found: {pdf_file}")
        sys.exit(1)

    pipe = PDFParsingPipeline(verbose=True)
    result = pipe.parse(pdf_file, chunk_size=c_size)
