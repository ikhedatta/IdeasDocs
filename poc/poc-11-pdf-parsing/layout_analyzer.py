"""Layout analysis — classify text regions by document role.

Phase 2: After text extraction, determine what each text box *is*
(title, header, body text, table, list item, etc.).

This POC uses heuristic rules tuned for resume-style documents.
Production should replace with a YOLO/LayoutLM model (like RAGFlow's
ONNX layout recognizer that classifies 11 region types).
"""

from __future__ import annotations

import logging
import re
import statistics
from typing import Sequence

from config import HEADER_FOOTER_MARGIN, TITLE_MIN_FONT_RATIO
from models import LayoutType, TextBox

logger = logging.getLogger(__name__)


class BaseLayoutAnalyzer:
    """Abstract layout analyzer — implement for model-based detection."""

    def analyze(
        self,
        text_boxes: list[TextBox],
        page_width: float,
        page_height: float,
    ) -> list[TextBox]:
        """Classify layout type for each text box in-place.

        Returns the same list with `layout_type` populated.
        """
        raise NotImplementedError


class HeuristicLayoutAnalyzer(BaseLayoutAnalyzer):
    """Rule-based layout classification for résumé-style documents.

    Heuristics (12 rules, ordered by priority):
    1. Header/Footer: top/bottom margin region
    2. Title: large font, short text, often bold
    3. Section Header: medium font, all-caps or title-case, short
    4. List Item: starts with bullet/dash/number
    5. Table: contains tab-separated columns or pipe characters
    6. Figure caption: starts with "Figure" / "Fig."
    7. Everything else: body text
    """

    # Patterns for list items
    _LIST_PATTERN = re.compile(
        r"^[\s]*(?:[•●○◦▪▸►\-–—]|\d{1,3}[.\)]\s|[a-zA-Z][.\)]\s|✓|✗)"
    )
    # Patterns for section headers (résumé sections)
    _SECTION_HEADERS = re.compile(
        r"^(?:experience|education|skills|summary|objective|projects|"
        r"certifications|awards|languages|interests|references|"
        r"work\s+history|professional\s+experience|technical\s+skills|"
        r"core\s+competencies|achievements|publications|"
        r"career\s+(?:objective|summary)|contact)\s*:?\s*$",
        re.IGNORECASE,
    )

    def analyze(
        self,
        text_boxes: list[TextBox],
        page_width: float,
        page_height: float,
    ) -> list[TextBox]:
        if not text_boxes:
            return text_boxes

        # Compute font size statistics for the page
        sizes = [b.font_size for b in text_boxes if b.font_size > 0]
        if sizes:
            median_size = statistics.median(sizes)
            max_size = max(sizes)
        else:
            median_size = 12.0
            max_size = 12.0

        for box in text_boxes:
            box.layout_type = self._classify_box(
                box, page_width, page_height, median_size, max_size,
            )

        return text_boxes

    def _classify_box(
        self,
        box: TextBox,
        page_width: float,
        page_height: float,
        median_font_size: float,
        max_font_size: float,
    ) -> LayoutType:
        text = box.text.strip()
        if not text:
            return LayoutType.TEXT

        # Rule 1: Header/Footer (top/bottom margin)
        if page_height > 0:
            y_ratio_top = box.bbox.y0 / page_height
            y_ratio_bottom = box.bbox.y1 / page_height
            if y_ratio_top < HEADER_FOOTER_MARGIN:
                return LayoutType.HEADER
            if y_ratio_bottom > (1 - HEADER_FOOTER_MARGIN):
                return LayoutType.FOOTER

        # Rule 2: Known section headers
        if self._SECTION_HEADERS.match(text):
            return LayoutType.TITLE

        # Rule 3: Title — large font, short text
        if (box.font_size > 0
                and median_font_size > 0
                and box.font_size >= median_font_size * TITLE_MIN_FONT_RATIO
                and len(text) < 100):
            return LayoutType.TITLE

        # Rule 4: Bold + short = section header
        if box.is_bold and len(text) < 80:
            # Check if it looks like a heading
            words = text.split()
            if len(words) <= 6 and not text.endswith((".","!","?")):
                return LayoutType.TITLE

        # Rule 5: List items
        if self._LIST_PATTERN.match(text):
            return LayoutType.LIST_ITEM

        # Rule 6: Table-like text (pipe-separated or tab-separated)
        if "|" in text and text.count("|") >= 2:
            return LayoutType.TABLE
        if "\t" in text and text.count("\t") >= 2:
            return LayoutType.TABLE

        # Rule 7: Figure captions
        if re.match(r"^(?:Figure|Fig\.?|Image|Photo)\s+\d", text, re.IGNORECASE):
            return LayoutType.CAPTION

        # Default: body text
        return LayoutType.TEXT
