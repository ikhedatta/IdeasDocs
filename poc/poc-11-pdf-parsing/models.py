"""Data models for the PDF parsing pipeline.

All intermediate and output data flows through these Pydantic models,
ensuring type safety and easy serialization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class PDFType(str, Enum):
    """Classification of PDF extraction strategy."""
    TEXT = "text"           # All text is directly extractable
    SCANNED = "scanned"    # Image-only pages, OCR required
    HYBRID = "hybrid"      # Mix of text and scanned pages
    DESIGN_TOOL = "design_tool"  # Canva/Figma — embedded subset fonts


class GarbleStrategy(str, Enum):
    """Which garble detection strategy triggered."""
    NONE = "none"
    PUA = "pua"                   # Private Use Area characters
    CID = "cid"                   # (cid:N) pdfminer placeholders
    FONT_ENCODING = "font_encoding"  # Subset font → ASCII punct mapping


class LayoutType(str, Enum):
    """Region classification for layout analysis."""
    TITLE = "title"
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    HEADER = "header"
    FOOTER = "footer"
    LIST_ITEM = "list_item"
    CAPTION = "caption"


class ChunkType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    TITLE = "title"


# ── Core Data Models ──────────────────────────────────────────────────

class BoundingBox(BaseModel):
    """Bounding box in page coordinates (points, 72 DPI base)."""
    x0: float
    y0: float  # top
    x1: float
    y1: float  # bottom
    page: int  # 0-indexed

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


class TextBox(BaseModel):
    """A single extracted text region from a PDF page."""
    text: str
    bbox: BoundingBox
    font_name: str = ""
    font_size: float = 0.0
    is_bold: bool = False
    confidence: float = 1.0  # 1.0 for direct extraction, <1 for OCR
    source: str = "text"     # "text" | "ocr"
    garble_strategy: GarbleStrategy = GarbleStrategy.NONE
    layout_type: LayoutType = LayoutType.TEXT
    column_id: int = 0


class PageResult(BaseModel):
    """Complete extraction result for a single PDF page."""
    page_number: int  # 0-indexed
    width: float
    height: float
    text_boxes: list[TextBox] = []
    pdf_type: PDFType = PDFType.TEXT
    garbled_box_count: int = 0
    ocr_box_count: int = 0
    total_box_count: int = 0
    processing_time_ms: float = 0.0


class DocumentResult(BaseModel):
    """Complete extraction result for an entire PDF document."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    filename: str
    page_count: int
    pdf_type: PDFType
    pages: list[PageResult] = []
    metadata: dict[str, Any] = {}
    processing_time_ms: float = 0.0
    total_text_boxes: int = 0
    total_garbled_boxes: int = 0
    total_ocr_boxes: int = 0


class Chunk(BaseModel):
    """A single chunk ready for embedding and indexing."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    document_id: str
    content: str
    chunk_type: ChunkType = ChunkType.TEXT
    token_count: int = 0
    chunk_index: int = 0  # position in document
    positions: list[dict] = []  # [{page, x0, y0, x1, y1}, ...]
    metadata: dict[str, Any] = {}
    # Populated by embedding hook
    embedding: Optional[list[float]] = None


class ParseResponse(BaseModel):
    """API response from the parse endpoint."""
    document_id: str
    filename: str
    pdf_type: str
    page_count: int
    chunk_count: int
    total_text_boxes: int
    garbled_boxes_detected: int
    ocr_boxes_used: int
    processing_time_ms: float
    chunks: list[Chunk]
