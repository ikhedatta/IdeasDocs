"""
PDF Parser using PyMuPDF (fitz).

RAGFlow Source: deepdoc/parser/pdf_parser.py

RAGFlow uses ONNX neural networks for layout detection and XGBoost for
text block merging. This POC uses PyMuPDF's built-in text extraction
with block-level structure, which provides a good baseline.

Upgrade Path:
- Level 1 (this): PyMuPDF text blocks with page tracking
- Level 2: Add `unstructured.io` for layout detection
- Level 3: Add ONNX layout models (RAGFlow's approach) for best quality
"""

import io
import fitz  # PyMuPDF
from chunkers.models import ContentBlock, BlockType
from .base import ParserRegistry


@ParserRegistry.register([".pdf"])
class PDFParser:
    """
    PDF parser using PyMuPDF with structure-aware extraction.
    
    Produces ContentBlocks with:
    - Block type detection (text, header, table heuristics)
    - Page numbers for source tracking
    - Bounding box positions for UI highlighting
    """

    def parse(
        self, file_bytes: bytes, filename: str, config: dict | None = None
    ) -> list[ContentBlock]:
        config = config or {}
        blocks: list[ContentBlock] = []

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # Optional: parse specific page ranges (RAGFlow pattern from parser_config)
        page_ranges = config.get("page_ranges")

        for page_num in range(len(doc)):
            # Skip pages outside configured ranges
            if page_ranges and not self._in_range(page_num + 1, page_ranges):
                continue

            page = doc[page_num]
            page_blocks = self._extract_page_blocks(page, page_num + 1)
            blocks.extend(page_blocks)

        doc.close()
        return blocks

    def _extract_page_blocks(self, page: fitz.Page, page_number: int) -> list[ContentBlock]:
        """
        Extract text blocks from a single PDF page.
        
        Uses PyMuPDF's get_text("dict") which returns structured blocks
        with bounding boxes, font info, and text content.
        """
        blocks = []
        page_dict = page.get_text("dict", sort=True)

        for block in page_dict.get("blocks", []):
            if block.get("type") == 0:  # Text block
                text = self._extract_block_text(block)
                if not text.strip():
                    continue

                # Detect block type from font characteristics
                block_type = self._detect_block_type(block, page)

                # Bounding box for UI source highlighting
                bbox = block.get("bbox", [0, 0, 0, 0])

                blocks.append(ContentBlock(
                    text=text.strip(),
                    block_type=block_type,
                    page_number=page_number,
                    position={
                        "x": round(bbox[0], 1),
                        "y": round(bbox[1], 1),
                        "w": round(bbox[2] - bbox[0], 1),
                        "h": round(bbox[3] - bbox[1], 1),
                    },
                ))

            elif block.get("type") == 1:  # Image block
                bbox = block.get("bbox", [0, 0, 0, 0])
                blocks.append(ContentBlock(
                    text="[Image]",
                    block_type=BlockType.FIGURE,
                    page_number=page_number,
                    position={
                        "x": round(bbox[0], 1),
                        "y": round(bbox[1], 1),
                        "w": round(bbox[2] - bbox[0], 1),
                        "h": round(bbox[3] - bbox[1], 1),
                    },
                ))

        return blocks

    def _extract_block_text(self, block: dict) -> str:
        """Extract all text from a block's lines and spans."""
        lines = []
        for line in block.get("lines", []):
            spans_text = []
            for span in line.get("spans", []):
                text = span.get("text", "")
                if text.strip():
                    spans_text.append(text)
            if spans_text:
                lines.append(" ".join(spans_text))
        return "\n".join(lines)

    def _detect_block_type(self, block: dict, page: fitz.Page) -> BlockType:
        """
        Heuristic block type detection from font characteristics.
        
        RAGFlow uses ONNX neural networks for this. This POC uses
        font size heuristics as a pragmatic starting point.
        
        Upgrade path: Replace with unstructured.io or ONNX models.
        """
        max_font_size = 0
        is_bold = False
        total_chars = 0

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = span.get("size", 12)
                flags = span.get("flags", 0)
                chars = len(span.get("text", ""))
                
                if chars > 0:
                    if size > max_font_size:
                        max_font_size = size
                    # Bit 4 = bold in PyMuPDF flags
                    if flags & (1 << 4):
                        is_bold = True
                    total_chars += chars

        # Simple heuristics for header detection
        text = self._extract_block_text(block)
        
        # Large or bold short text → likely header
        if max_font_size > 14 and total_chars < 200:
            return BlockType.HEADER
        if is_bold and total_chars < 100 and "\n" not in text:
            return BlockType.HEADER

        # Table detection heuristic: lots of tab characters or pipe chars
        if text.count("|") > 4 or text.count("\t") > 3:
            return BlockType.TABLE

        # Check for list patterns
        lines = text.strip().split("\n")
        if len(lines) > 2:
            list_markers = sum(
                1 for line in lines
                if line.strip() and (
                    line.strip()[0] in "•●○◦-–—" or
                    (len(line.strip()) > 2 and line.strip()[0].isdigit() and line.strip()[1] in ".)")
                )
            )
            if list_markers > len(lines) * 0.5:
                return BlockType.LIST

        return BlockType.TEXT

    def _in_range(self, page_num: int, ranges: list[list[int]]) -> bool:
        """Check if page number falls within any configured range."""
        for start, end in ranges:
            if start <= page_num <= end:
                return True
        return False
