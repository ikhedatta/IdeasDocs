"""Text extraction from PDFs with garble detection and OCR fallback.

This is Phase 1 of the pipeline — the critical module that handles
Canva-style PDFs where standard text extraction produces garbage.

Strategy (inspired by RAGFlow's per-box hybrid approach):
1. Extract text + character metadata from each page via pdfplumber
2. Also extract via PyMuPDF (fitz) for comparison / fallback
3. For each text region, run garble detection
4. If garbled → flag for OCR fallback (handled by ocr_engine.py)
5. If clean → use the extracted text directly

The dual-library approach (pdfplumber + PyMuPDF) catches more edge
cases: PyMuPDF sometimes resolves CID mappings that pdfplumber misses,
and vice versa.
"""

from __future__ import annotations

import logging
import re
from timeit import default_timer as timer
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

from classifier import (
    classify_page,
    detect_garble_strategy,
    has_subset_font_prefix,
)
from config import PAGE_DPI, PAGE_ZOOM
from models import BoundingBox, GarbleStrategy, PageResult, PDFType, TextBox

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extract text boxes from a PDF page using pdfplumber + PyMuPDF.

    For each text region:
    - If pdfplumber text is clean → use it (preserves exact coordinates)
    - If garbled → try PyMuPDF extraction for the same region
    - If still garbled → mark for OCR (caller handles the OCR step)
    """

    def extract_page(
        self,
        pdf_path: str,
        page_number: int,
    ) -> tuple[PageResult, Optional[Image.Image]]:
        """Extract text boxes and page image from a single PDF page.

        Args:
            pdf_path: Path to the PDF file.
            page_number: 0-indexed page number.

        Returns:
            Tuple of (PageResult with text boxes, page image for OCR).
        """
        start = timer()
        text_boxes: list[TextBox] = []
        page_image: Optional[Image.Image] = None
        width = height = 0.0
        garbled_count = 0

        # ── pdfplumber extraction ──────────────────────────────────
        try:
            plumber_boxes, plumber_chars_by_box, width, height = (
                self._extract_pdfplumber(pdf_path, page_number)
            )
        except Exception as e:
            logger.warning("pdfplumber failed on page %d: %s", page_number, e)
            plumber_boxes = []
            plumber_chars_by_box = []

        # ── PyMuPDF extraction (for comparison / fallback) ─────────
        try:
            fitz_blocks = self._extract_pymupdf(pdf_path, page_number)
        except Exception as e:
            logger.warning("PyMuPDF failed on page %d: %s", page_number, e)
            fitz_blocks = []

        # ── Garble detection per box ───────────────────────────────
        for i, (box, chars) in enumerate(zip(plumber_boxes, plumber_chars_by_box)):
            text = box["text"]
            strategy = detect_garble_strategy(text, chars)

            if strategy != GarbleStrategy.NONE:
                # Try PyMuPDF text for the same region
                fitz_text = self._find_fitz_text_for_region(
                    fitz_blocks, box["bbox"], tolerance=5.0
                )
                if fitz_text and detect_garble_strategy(fitz_text) == GarbleStrategy.NONE:
                    # PyMuPDF resolved it — use its text
                    logger.debug(
                        "Page %d box %d: pdfplumber garbled (%s), PyMuPDF resolved",
                        page_number, i, strategy.value,
                    )
                    text_boxes.append(TextBox(
                        text=fitz_text.strip(),
                        bbox=BoundingBox(
                            x0=box["bbox"][0], y0=box["bbox"][1],
                            x1=box["bbox"][2], y1=box["bbox"][3],
                            page=page_number,
                        ),
                        font_name=box.get("fontname", ""),
                        font_size=box.get("size", 0.0),
                        source="fitz",
                        garble_strategy=GarbleStrategy.NONE,
                    ))
                else:
                    # Both libraries failed — mark for OCR
                    garbled_count += 1
                    text_boxes.append(TextBox(
                        text="",  # Empty → OCR will fill this
                        bbox=BoundingBox(
                            x0=box["bbox"][0], y0=box["bbox"][1],
                            x1=box["bbox"][2], y1=box["bbox"][3],
                            page=page_number,
                        ),
                        font_name=box.get("fontname", ""),
                        font_size=box.get("size", 0.0),
                        source="ocr_pending",
                        garble_strategy=strategy,
                    ))
            else:
                # Clean text from pdfplumber
                if text.strip():
                    text_boxes.append(TextBox(
                        text=text.strip(),
                        bbox=BoundingBox(
                            x0=box["bbox"][0], y0=box["bbox"][1],
                            x1=box["bbox"][2], y1=box["bbox"][3],
                            page=page_number,
                        ),
                        font_name=box.get("fontname", ""),
                        font_size=box.get("size", 0.0),
                        is_bold="bold" in box.get("fontname", "").lower(),
                        source="text",
                    ))

        # ── If any garbled or scanned → render page image for OCR ──
        needs_ocr = garbled_count > 0 or len(text_boxes) == 0
        if needs_ocr:
            page_image = self._render_page_image(pdf_path, page_number)

        # ── Also check for regions pdfplumber missed entirely ──────
        if fitz_blocks and len(text_boxes) < len(fitz_blocks) // 2:
            # pdfplumber missed a lot — add fitz-only blocks
            for block in fitz_blocks:
                if not self._region_covered(block["bbox"], text_boxes):
                    ft = block["text"].strip()
                    if ft:
                        text_boxes.append(TextBox(
                            text=ft,
                            bbox=BoundingBox(
                                x0=block["bbox"][0], y0=block["bbox"][1],
                                x1=block["bbox"][2], y1=block["bbox"][3],
                                page=page_number,
                            ),
                            source="fitz",
                        ))

        elapsed_ms = (timer() - start) * 1000

        # ── Classify page type ─────────────────────────────────────
        total_chars = sum(len(b.text) for b in text_boxes)
        garble_ratio = garbled_count / max(len(text_boxes), 1)
        page_type = classify_page(
            extractable_char_count=total_chars,
            total_visible_area=sum(b.bbox.area for b in text_boxes),
            page_area=width * height if width and height else 1.0,
            garble_ratio=garble_ratio,
        )

        return PageResult(
            page_number=page_number,
            width=width,
            height=height,
            text_boxes=text_boxes,
            pdf_type=page_type,
            garbled_box_count=garbled_count,
            ocr_box_count=0,  # Updated after OCR phase
            total_box_count=len(text_boxes),
            processing_time_ms=elapsed_ms,
        ), page_image

    # ── pdfplumber: word-level extraction with char metadata ───────

    def _extract_pdfplumber(
        self, pdf_path: str, page_number: int
    ) -> tuple[list[dict], list[list[dict]], float, float]:
        """Extract words and their character metadata from pdfplumber.

        Returns:
            (word_boxes, chars_per_box, page_width, page_height)
        """
        boxes: list[dict] = []
        chars_by_box: list[list[dict]] = []

        with pdfplumber.open(pdf_path) as pdf:
            if page_number >= len(pdf.pages):
                return [], [], 0, 0
            page = pdf.pages[page_number]
            width = float(page.width)
            height = float(page.height)

            # Extract words with bounding boxes
            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=False,
                extra_attrs=["fontname", "size"],
            )

            chars = page.chars  # All characters with full metadata

            for word in words:
                box = {
                    "text": word["text"],
                    "bbox": (word["x0"], word["top"], word["x1"], word["bottom"]),
                    "fontname": word.get("fontname", ""),
                    "size": word.get("size", 0),
                }
                # Collect characters belonging to this word's bounding box
                word_chars = [
                    c for c in chars
                    if (c["x0"] >= word["x0"] - 1
                        and c["x1"] <= word["x1"] + 1
                        and c["top"] >= word["top"] - 1
                        and c["bottom"] <= word["bottom"] + 1)
                ]
                boxes.append(box)
                chars_by_box.append(word_chars)

        return boxes, chars_by_box, width, height

    # ── PyMuPDF: block-level extraction ────────────────────────────

    def _extract_pymupdf(self, pdf_path: str, page_number: int) -> list[dict]:
        """Extract text blocks from PyMuPDF (fitz).

        PyMuPDF has a different font resolution engine and sometimes
        handles CID mappings that pdfplumber misses.
        """
        blocks = []
        doc = fitz.open(pdf_path)
        try:
            if page_number >= doc.page_count:
                return []
            page = doc[page_number]
            # "dict" output gives us blocks with spans containing font info
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in page_dict.get("blocks", []):
                if block["type"] != 0:  # text blocks only
                    continue
                texts = []
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        texts.append(span["text"])
                full_text = " ".join(texts)
                if full_text.strip():
                    blocks.append({
                        "text": full_text,
                        "bbox": (
                            block["bbox"][0], block["bbox"][1],
                            block["bbox"][2], block["bbox"][3],
                        ),
                    })
        finally:
            doc.close()
        return blocks

    # ── Region matching between pdfplumber and PyMuPDF ─────────────

    @staticmethod
    def _find_fitz_text_for_region(
        fitz_blocks: list[dict],
        target_bbox: tuple,
        tolerance: float = 5.0,
    ) -> str:
        """Find PyMuPDF text that overlaps with a pdfplumber bounding box."""
        tx0, ty0, tx1, ty1 = target_bbox
        best_text = ""
        best_overlap = 0.0

        for block in fitz_blocks:
            bx0, by0, bx1, by1 = block["bbox"]
            # Calculate overlap area
            ox0 = max(tx0, bx0)
            oy0 = max(ty0, by0)
            ox1 = min(tx1, bx1)
            oy1 = min(ty1, by1)
            if ox0 < ox1 and oy0 < oy1:
                overlap = (ox1 - ox0) * (oy1 - oy0)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_text = block["text"]

        return best_text

    @staticmethod
    def _region_covered(bbox: tuple, existing_boxes: list[TextBox], threshold: float = 0.5) -> bool:
        """Check if a bounding box is already covered by existing text boxes."""
        bx0, by0, bx1, by1 = bbox
        b_area = (bx1 - bx0) * (by1 - by0)
        if b_area <= 0:
            return True  # degenerate box

        for tb in existing_boxes:
            ox0 = max(bx0, tb.bbox.x0)
            oy0 = max(by0, tb.bbox.y0)
            ox1 = min(bx1, tb.bbox.x1)
            oy1 = min(by1, tb.bbox.y1)
            if ox0 < ox1 and oy0 < oy1:
                overlap = (ox1 - ox0) * (oy1 - oy0)
                if overlap / b_area >= threshold:
                    return True
        return False

    # ── Page image rendering ───────────────────────────────────────

    @staticmethod
    def _render_page_image(pdf_path: str, page_number: int) -> Image.Image:
        """Render a PDF page as a high-DPI PIL Image for OCR."""
        doc = fitz.open(pdf_path)
        try:
            page = doc[page_number]
            mat = fitz.Matrix(PAGE_ZOOM, PAGE_ZOOM)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            return img
        finally:
            doc.close()
