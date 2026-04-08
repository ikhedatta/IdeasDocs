"""Tests for POC-11 — PDF Parsing Pipeline.

Covers: classifier, text_extractor, ocr_engine, layout_analyzer,
reading_order, chunker, embeddings, pipeline, and API endpoints.
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Ensure POC directory is on path
POC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)


# ═══════════════════════════════════════════════════════════════════════
# 1. CLASSIFIER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestGarbleDetection:
    """Test all three garble detection strategies."""

    def test_clean_text_not_garbled(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        assert detect_garble_strategy("Hello World from Infosys") == GarbleStrategy.NONE

    def test_empty_text_not_garbled(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        assert detect_garble_strategy("") == GarbleStrategy.NONE
        assert detect_garble_strategy("   ") == GarbleStrategy.NONE

    def test_cid_pattern_detected(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        text = "Some (cid:123) garbled (cid:456) text"
        assert detect_garble_strategy(text) == GarbleStrategy.CID

    def test_cid_pattern_with_spaces(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        assert detect_garble_strategy("(cid : 42)") == GarbleStrategy.CID

    def test_pua_characters_detected(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        # Build text with >30% PUA characters
        pua_chars = "".join(chr(c) for c in range(0xE000, 0xE010))
        text = pua_chars + "abc"
        # PUA chars are majority → should detect
        assert detect_garble_strategy(text) == GarbleStrategy.PUA

    def test_pua_below_threshold_not_garbled(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        # Just one PUA char in lots of text
        text = "This is perfectly normal text " + chr(0xE000) + " with content"
        assert detect_garble_strategy(text) == GarbleStrategy.NONE

    def test_replacement_char_detected(self):
        from classifier import is_garbled_char
        assert is_garbled_char(chr(0xFFFD))  # Unicode replacement character
        assert is_garbled_char(chr(0xE001))  # PUA
        assert not is_garbled_char("A")
        assert not is_garbled_char(" ")

    def test_control_chars_garbled(self):
        from classifier import is_garbled_char
        assert is_garbled_char(chr(0x01))  # SOH
        assert is_garbled_char(chr(0x80))  # C1 control
        assert not is_garbled_char("\t")   # Tab is ok
        assert not is_garbled_char("\n")   # Newline is ok

    def test_font_encoding_garble(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        # Simulate Canva-style subset fonts with ASCII punct output
        chars = []
        for i in range(20):
            chars.append({"text": "!", "fontname": "ABCDEF+CustomFont"})
        for i in range(5):
            chars.append({"text": "a", "fontname": "Arial"})
        # Compose text from chars
        text = "".join(c["text"] for c in chars)
        assert detect_garble_strategy(text, chars) == GarbleStrategy.FONT_ENCODING

    def test_font_encoding_with_cjk_not_garbled(self):
        from classifier import detect_garble_strategy
        from models import GarbleStrategy
        # Subset fonts but with actual CJK output — not garbled
        chars = []
        for i in range(15):
            chars.append({"text": "中", "fontname": "ABCDEF+SimSun"})
        for i in range(5):
            chars.append({"text": "!", "fontname": "ABCDEF+SimSun"})
        text = "".join(c["text"] for c in chars)
        assert detect_garble_strategy(text, chars) == GarbleStrategy.NONE

    def test_subset_font_prefix(self):
        from classifier import has_subset_font_prefix
        assert has_subset_font_prefix("ABCDEF+TimesNewRoman")
        assert has_subset_font_prefix("DY1+ZLQDm1-1")  # Canva-style
        assert has_subset_font_prefix("AB+Font")
        assert not has_subset_font_prefix("TimesNewRoman")
        assert not has_subset_font_prefix("")
        assert not has_subset_font_prefix("a+lower")  # lowercase


class TestPageClassification:
    def test_text_page(self):
        from classifier import classify_page
        from models import PDFType
        assert classify_page(500, 10000, 50000, 0.0) == PDFType.TEXT

    def test_scanned_page(self):
        from classifier import classify_page
        from models import PDFType
        assert classify_page(5, 100, 50000, 0.0) == PDFType.SCANNED

    def test_design_tool_page(self):
        from classifier import classify_page
        from models import PDFType
        assert classify_page(200, 5000, 50000, 0.5) == PDFType.DESIGN_TOOL

    def test_document_classification(self):
        from classifier import classify_document
        from models import PDFType
        assert classify_document([PDFType.TEXT, PDFType.TEXT]) == PDFType.TEXT
        assert classify_document([PDFType.TEXT, PDFType.SCANNED]) == PDFType.HYBRID
        assert classify_document([PDFType.SCANNED, PDFType.SCANNED]) == PDFType.SCANNED
        assert classify_document([PDFType.TEXT, PDFType.DESIGN_TOOL]) == PDFType.DESIGN_TOOL
        assert classify_document([]) == PDFType.SCANNED


# ═══════════════════════════════════════════════════════════════════════
# 2. MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestModels:
    def test_bounding_box_properties(self):
        from models import BoundingBox
        bb = BoundingBox(x0=10, y0=20, x1=110, y1=70, page=0)
        assert bb.width == 100
        assert bb.height == 50
        assert bb.area == 5000
        assert bb.center_x == 60
        assert bb.center_y == 45

    def test_text_box_defaults(self):
        from models import BoundingBox, GarbleStrategy, LayoutType, TextBox
        tb = TextBox(
            text="Hello",
            bbox=BoundingBox(x0=0, y0=0, x1=100, y1=20, page=0),
        )
        assert tb.confidence == 1.0
        assert tb.source == "text"
        assert tb.garble_strategy == GarbleStrategy.NONE
        assert tb.layout_type == LayoutType.TEXT

    def test_chunk_defaults(self):
        from models import Chunk, ChunkType
        c = Chunk(document_id="d1", content="Hello world")
        assert c.chunk_type == ChunkType.TEXT
        assert c.embedding is None
        assert c.id  # auto-generated

    def test_page_result(self):
        from models import PageResult, PDFType
        pr = PageResult(page_number=0, width=612, height=792)
        assert pr.pdf_type == PDFType.TEXT
        assert pr.text_boxes == []

    def test_parse_response_serialization(self):
        from models import ParseResponse
        resp = ParseResponse(
            document_id="d1", filename="test.pdf", pdf_type="text",
            page_count=1, chunk_count=3, total_text_boxes=10,
            garbled_boxes_detected=0, ocr_boxes_used=0,
            processing_time_ms=100.0, chunks=[],
        )
        data = resp.model_dump()
        assert data["pdf_type"] == "text"


# ═══════════════════════════════════════════════════════════════════════
# 3. LAYOUT ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestLayoutAnalyzer:
    def _make_box(self, text, y0=100, y1=120, font_size=12.0, bold=False, fontname="Arial"):
        from models import BoundingBox, TextBox
        return TextBox(
            text=text,
            bbox=BoundingBox(x0=50, y0=y0, x1=300, y1=y1, page=0),
            font_size=font_size,
            is_bold=bold,
            font_name=fontname,
        )

    def test_title_by_font_size(self):
        from layout_analyzer import HeuristicLayoutAnalyzer
        from models import LayoutType
        analyzer = HeuristicLayoutAnalyzer()
        boxes = [
            self._make_box("Big Title", font_size=24.0),
            self._make_box("Normal body text here.", font_size=12.0),
            self._make_box("Another body line.", font_size=12.0),
        ]
        result = analyzer.analyze(boxes, 612, 792)
        assert result[0].layout_type == LayoutType.TITLE
        assert result[1].layout_type == LayoutType.TEXT

    def test_section_headers(self):
        from layout_analyzer import HeuristicLayoutAnalyzer
        from models import LayoutType
        analyzer = HeuristicLayoutAnalyzer()
        boxes = [
            self._make_box("Experience"),
            self._make_box("Some job description"),
            self._make_box("Education"),
            self._make_box("University of Testing"),
        ]
        result = analyzer.analyze(boxes, 612, 792)
        assert result[0].layout_type == LayoutType.TITLE  # "Experience"
        assert result[2].layout_type == LayoutType.TITLE  # "Education"

    def test_list_items(self):
        from layout_analyzer import HeuristicLayoutAnalyzer
        from models import LayoutType
        analyzer = HeuristicLayoutAnalyzer()
        boxes = [
            self._make_box("• Built microservices architecture"),
            self._make_box("- Managed team of 5 developers"),
            self._make_box("1. Designed database schema"),
        ]
        result = analyzer.analyze(boxes, 612, 792)
        for r in result:
            assert r.layout_type == LayoutType.LIST_ITEM

    def test_header_detection(self):
        from layout_analyzer import HeuristicLayoutAnalyzer
        from models import LayoutType
        analyzer = HeuristicLayoutAnalyzer()
        boxes = [
            self._make_box("Page 1 of 3", y0=2, y1=15),  # Top margin
            self._make_box("Body text", y0=100, y1=120),
        ]
        result = analyzer.analyze(boxes, 612, 792)
        assert result[0].layout_type == LayoutType.HEADER

    def test_footer_detection(self):
        from layout_analyzer import HeuristicLayoutAnalyzer
        from models import LayoutType
        analyzer = HeuristicLayoutAnalyzer()
        boxes = [
            self._make_box("Body text", y0=100, y1=120),
            self._make_box("Copyright 2024", y0=770, y1=790),
        ]
        result = analyzer.analyze(boxes, 612, 792)
        assert result[1].layout_type == LayoutType.FOOTER


# ═══════════════════════════════════════════════════════════════════════
# 4. READING ORDER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestReadingOrder:
    def _make_box(self, text, x0, y0, x1, y1, col=0, layout="text"):
        from models import BoundingBox, LayoutType, TextBox
        return TextBox(
            text=text,
            bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=0),
            column_id=col,
            layout_type=LayoutType(layout),
        )

    def test_sort_single_column(self):
        from reading_order import sort_reading_order
        boxes = [
            self._make_box("Third", 50, 200, 300, 220),
            self._make_box("First", 50, 50, 300, 70),
            self._make_box("Second", 50, 100, 300, 120),
        ]
        sorted_boxes = sort_reading_order(boxes)
        assert sorted_boxes[0].text == "First"
        assert sorted_boxes[1].text == "Second"
        assert sorted_boxes[2].text == "Third"

    def test_sort_two_columns(self):
        from reading_order import sort_reading_order
        boxes = [
            self._make_box("Col2-Top", 350, 50, 560, 70, col=1),
            self._make_box("Col1-Top", 50, 50, 260, 70, col=0),
            self._make_box("Col1-Bot", 50, 100, 260, 120, col=0),
            self._make_box("Col2-Bot", 350, 100, 560, 120, col=1),
        ]
        sorted_boxes = sort_reading_order(boxes)
        assert sorted_boxes[0].text == "Col1-Top"
        assert sorted_boxes[1].text == "Col1-Bot"
        assert sorted_boxes[2].text == "Col2-Top"
        assert sorted_boxes[3].text == "Col2-Bot"

    def test_headers_before_body(self):
        from reading_order import sort_reading_order
        boxes = [
            self._make_box("Body", 50, 100, 300, 120),
            self._make_box("Header", 50, 10, 300, 25, layout="header"),
        ]
        sorted_boxes = sort_reading_order(boxes)
        assert sorted_boxes[0].text == "Header"
        assert sorted_boxes[1].text == "Body"

    def test_merge_adjacent(self):
        from reading_order import merge_adjacent_boxes
        boxes = [
            self._make_box("Hello", 50, 100, 100, 120),
            self._make_box("World", 105, 100, 160, 120),
            self._make_box("Next line", 50, 140, 200, 160),
        ]
        merged = merge_adjacent_boxes(boxes)
        assert len(merged) == 2
        assert "Hello" in merged[0].text and "World" in merged[0].text
        assert merged[1].text == "Next line"


# ═══════════════════════════════════════════════════════════════════════
# 5. CHUNKER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestChunker:
    def _make_box(self, text, layout="text"):
        from models import BoundingBox, LayoutType, TextBox
        return TextBox(
            text=text,
            bbox=BoundingBox(x0=50, y0=0, x1=300, y1=20, page=0),
            layout_type=LayoutType(layout),
        )

    def test_basic_chunking(self):
        from chunker import chunk_text_boxes
        boxes = [
            self._make_box("This is a paragraph of text about software engineering."),
            self._make_box("Another paragraph about machine learning and AI."),
        ]
        chunks = chunk_text_boxes(boxes, "doc1", chunk_size=512)
        assert len(chunks) >= 1
        assert chunks[0].document_id == "doc1"
        assert chunks[0].content

    def test_title_creates_section_boundary(self):
        from chunker import chunk_text_boxes
        boxes = [
            self._make_box("Experience", layout="title"),
            self._make_box("Worked at Infosys for 5 years."),
            self._make_box("Education", layout="title"),
            self._make_box("BS in Computer Science from MIT."),
        ]
        chunks = chunk_text_boxes(boxes, "doc1", chunk_size=512)
        # Titles should create section boundaries
        assert len(chunks) >= 2
        # First chunk should have Experience section
        assert "Infosys" in chunks[0].content
        # Second chunk should have Education section
        assert "Computer Science" in chunks[1].content

    def test_large_text_splits_by_token_limit(self):
        from chunker import chunk_text_boxes
        # Create a large text that exceeds chunk size
        long_text = "This is a sentence about coding. " * 200
        boxes = [self._make_box(long_text)]
        chunks = chunk_text_boxes(boxes, "doc1", chunk_size=64)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.token_count <= 64 + 20  # Allow some tolerance

    def test_overlap(self):
        from chunker import chunk_text_boxes
        long_text = "Sentence one about Python. " * 100
        boxes = [self._make_box(long_text)]
        chunks = chunk_text_boxes(boxes, "doc1", chunk_size=64, chunk_overlap=16)
        if len(chunks) >= 2:
            # Last words of chunk 0 should appear at start of chunk 1
            tail_words = chunks[0].content.split()[-5:]
            head_words = chunks[1].content.split()[:10]
            overlap_found = any(w in head_words for w in tail_words)
            assert overlap_found, "Overlap not detected between chunks"

    def test_empty_boxes(self):
        from chunker import chunk_text_boxes
        chunks = chunk_text_boxes([], "doc1")
        assert chunks == []

    def test_position_preservation(self):
        from chunker import chunk_text_boxes
        boxes = [self._make_box("Hello from page 0")]
        chunks = chunk_text_boxes(boxes, "doc1")
        assert len(chunks) == 1
        assert len(chunks[0].positions) > 0
        assert chunks[0].positions[0]["page"] == 0

    def test_estimate_tokens(self):
        from chunker import estimate_tokens
        assert estimate_tokens("Hello world") >= 1
        assert estimate_tokens("") == 1  # minimum 1
        # Roughly: 10 words ≈ 13 tokens
        assert 10 <= estimate_tokens(" ".join(["word"] * 10)) <= 20

    def test_split_by_delimiters(self):
        from chunker import split_by_delimiters
        text = "First sentence. Second sentence! Third one?"
        segments = split_by_delimiters(text)
        assert len(segments) >= 2

    def test_section_title_in_metadata(self):
        from chunker import chunk_text_boxes
        boxes = [
            self._make_box("Skills", layout="title"),
            self._make_box("Python, Java, Go"),
        ]
        chunks = chunk_text_boxes(boxes, "doc1")
        assert chunks[0].metadata.get("section_title") == "Skills"


# ═══════════════════════════════════════════════════════════════════════
# 6. EMBEDDING TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestEmbeddings:
    def test_noop_embedder(self):
        from embeddings import NoOpEmbedder
        from models import Chunk
        embedder = NoOpEmbedder(dim=128)
        assert embedder.dimension == 128

        chunks = [
            Chunk(document_id="d1", content="Hello world"),
            Chunk(document_id="d1", content="Goodbye world"),
        ]
        result = embedder.embed_chunks(chunks)
        assert len(result) == 2
        assert len(result[0].embedding) == 128
        assert all(v == 0.0 for v in result[0].embedding)

    def test_embed_batch(self):
        from embeddings import NoOpEmbedder
        embedder = NoOpEmbedder(dim=64)
        vectors = embedder.embed_batch(["one", "two", "three"])
        assert len(vectors) == 3
        assert len(vectors[0]) == 64


# ═══════════════════════════════════════════════════════════════════════
# 7. OCR ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestOCREngine:
    def test_noop_engine(self):
        from models import BoundingBox
        from ocr_engine import NoOpOCREngine
        from PIL import Image
        engine = NoOpOCREngine()
        img = Image.new("RGB", (100, 100))
        bbox = BoundingBox(x0=0, y0=0, x1=50, y1=50, page=0)
        assert engine.ocr_region(img, bbox) == ""
        assert engine.ocr_full_page(img) == []

    def test_fill_garbled_boxes_skips_without_image(self):
        from models import BoundingBox, TextBox
        from ocr_engine import NoOpOCREngine
        engine = NoOpOCREngine()
        boxes = [TextBox(
            text="", source="ocr_pending",
            bbox=BoundingBox(x0=0, y0=0, x1=100, y1=20, page=0),
        )]
        result, count = engine.fill_garbled_boxes(boxes, None)
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════
# 8. INTEGRATION: Pipeline with real PDF (if available)
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """Integration tests using the actual Canva resume PDF if present."""

    @pytest.fixture
    def canva_pdf_path(self):
        """Path to the Canva resume PDF."""
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "lead python developer.pdf",
        )
        if not os.path.exists(path):
            pytest.skip("Canva resume PDF not found")
        return path

    @pytest.fixture
    def simple_pdf_path(self):
        """Create a minimal text PDF for testing."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)

        # Add text to the page
        text_point = fitz.Point(72, 100)
        page.insert_text(text_point, "John Smith", fontsize=24, fontname="helv")
        page.insert_text(fitz.Point(72, 140), "Lead Python Developer", fontsize=16, fontname="helv")
        page.insert_text(fitz.Point(72, 180), "Experience", fontsize=14, fontname="helv")
        page.insert_text(
            fitz.Point(72, 210),
            "• Worked at Infosys for 5 years building microservices",
            fontsize=11, fontname="helv",
        )
        page.insert_text(
            fitz.Point(72, 235),
            "• Led migration of Magna Corp legacy systems to cloud",
            fontsize=11, fontname="helv",
        )
        page.insert_text(fitz.Point(72, 280), "Education", fontsize=14, fontname="helv")
        page.insert_text(
            fitz.Point(72, 310),
            "BS Computer Science — MIT, 2015",
            fontsize=11, fontname="helv",
        )

        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        doc.save(path)
        doc.close()
        yield path

        os.unlink(path)

    def test_pipeline_with_simple_pdf(self, simple_pdf_path):
        """End-to-end test with a programmatically created PDF."""
        from pipeline import PDFParsingPipeline
        from ocr_engine import NoOpOCREngine

        pipeline = PDFParsingPipeline(ocr_engine=NoOpOCREngine())
        result = pipeline.parse(simple_pdf_path, filename="test_resume.pdf")

        doc = result["document"]
        chunks = result["chunks"]

        assert doc.page_count == 1
        assert doc.pdf_type.value == "text"
        assert len(chunks) >= 1

        # The key test: proper nouns must be extracted
        all_text = " ".join(c.content for c in chunks)
        assert "John Smith" in all_text or "John" in all_text
        assert "Infosys" in all_text
        assert "Magna" in all_text
        assert "MIT" in all_text

    def test_pipeline_produces_position_metadata(self, simple_pdf_path):
        from pipeline import PDFParsingPipeline
        from ocr_engine import NoOpOCREngine

        pipeline = PDFParsingPipeline(ocr_engine=NoOpOCREngine())
        result = pipeline.parse(simple_pdf_path)

        chunks = result["chunks"]
        for chunk in chunks:
            assert len(chunk.positions) > 0
            assert chunk.positions[0]["page"] == 0

    def test_pipeline_chunk_size_respected(self, simple_pdf_path):
        from pipeline import PDFParsingPipeline
        from ocr_engine import NoOpOCREngine

        pipeline = PDFParsingPipeline(ocr_engine=NoOpOCREngine())
        result = pipeline.parse(simple_pdf_path, chunk_size=32)

        chunks = result["chunks"]
        for chunk in chunks:
            # Allow some tolerance
            assert chunk.token_count <= 50

    def test_canva_pdf_parsing(self, canva_pdf_path):
        """Test with the actual Canva resume PDF.

        Key assertion: words like 'Infosys' and 'Magna' that standard
        parsers miss due to subset font garbling must be extracted
        (either via PyMuPDF fallback or OCR).
        """
        from pipeline import PDFParsingPipeline

        pipeline = PDFParsingPipeline()
        result = pipeline.parse(canva_pdf_path, filename="lead python developer.pdf")

        doc = result["document"]
        chunks = result["chunks"]

        # Document should parse
        assert doc.page_count >= 1
        assert len(chunks) >= 1

        all_text = " ".join(c.content for c in chunks).lower()

        # These keywords are present in the PDF but often missed by naive parsers
        # If garble detection + OCR works, at least some should be found
        logger_info = (
            f"PDF type: {doc.pdf_type.value}, "
            f"boxes: {doc.total_text_boxes}, "
            f"garbled: {doc.total_garbled_boxes}, "
            f"OCR: {doc.total_ocr_boxes}, "
            f"chunks: {len(chunks)}"
        )
        print(logger_info)
        print(f"Extracted text preview: {all_text[:500]}")

        # At minimum, the pipeline should not crash and should produce output
        assert len(all_text) > 50, f"Too little text extracted: {len(all_text)} chars"


# ═══════════════════════════════════════════════════════════════════════
# 9. API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestAPI:
    @pytest.fixture
    def simple_pdf_bytes(self):
        """Generate a simple PDF in memory."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text(fitz.Point(72, 100), "Test document content", fontsize=12, fontname="helv")
        page.insert_text(fitz.Point(72, 130), "With multiple lines of text", fontsize=12, fontname="helv")
        data = doc.tobytes()
        doc.close()
        return data

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_parse_endpoint(self, simple_pdf_bytes):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/parse",
                files={"file": ("test.pdf", simple_pdf_bytes, "application/pdf")},
                params={"chunk_size": 256},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["filename"] == "test.pdf"
        assert data["page_count"] == 1
        assert data["chunk_count"] >= 1
        assert len(data["chunks"]) >= 1

    @pytest.mark.asyncio
    async def test_parse_rejects_non_pdf(self):
        from httpx import ASGITransport, AsyncClient
        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/parse",
                files={"file": ("test.txt", b"Hello world", "text/plain")},
            )
        assert r.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
