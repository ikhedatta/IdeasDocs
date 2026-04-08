"""PDF type classifier — determines extraction strategy before heavy processing.

Inspired by RAGFlow's approach: examine character metadata from pdfplumber
to decide whether the document needs OCR, and specifically detect
design-tool PDFs (Canva, Figma) that produce garbled text.

This is Phase 0 of the pipeline — it runs fast and avoids wasting time
on the wrong extraction path.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Sequence

from config import (
    GARBLE_CJK_RATIO_MAX,
    GARBLE_MIN_CHARS,
    GARBLE_PUA_THRESHOLD,
    GARBLE_PUNCT_RATIO_MIN,
    GARBLE_SUBSET_FONT_RATIO,
)
from models import GarbleStrategy, PDFType

logger = logging.getLogger(__name__)

# Regex for pdfminer CID placeholders
_CID_PATTERN = re.compile(r"\(cid\s*:\s*\d+\s*\)")

# Regex for subset font prefix (e.g., "ABCDEF+FontName" or "DY1+Font")
_SUBSET_FONT_RE = re.compile(r"^[A-Z0-9]{2,6}\+")


# ── Character-Level Garble Detection ──────────────────────────────────

def is_garbled_char(ch: str) -> bool:
    """Check if a character is garbled (PUA, replacement, control).

    Mirrors RAGFlow's `_is_garbled_char` exactly.
    """
    if not ch:
        return False
    cp = ord(ch)
    # Private Use Areas
    if 0xE000 <= cp <= 0xF8FF:
        return True
    if 0xF0000 <= cp <= 0xFFFFF:
        return True
    if 0x100000 <= cp <= 0x10FFFF:
        return True
    # Replacement character
    if cp == 0xFFFD:
        return True
    # Non-printable control characters (except whitespace)
    if cp < 0x20 and ch not in ("\t", "\n", "\r"):
        return True
    # C1 control characters
    if 0x80 <= cp <= 0x9F:
        return True
    # Unassigned / surrogate
    cat = unicodedata.category(ch)
    if cat in ("Cn", "Cs"):
        return True
    return False


def has_subset_font_prefix(fontname: str) -> bool:
    """Detect subset font prefix like 'ABCDEF+FontName' or 'DY1+Font'."""
    if not fontname:
        return False
    return bool(_SUBSET_FONT_RE.match(fontname))


# ── Text-Level Garble Detection ──────────────────────────────────────

def detect_garble_strategy(text: str, chars: Sequence[dict] | None = None) -> GarbleStrategy:
    """Determine which garble strategy (if any) applies to a text region.

    Implements all three RAGFlow detection strategies:
    1. CID pattern: `(cid:123)` placeholders from pdfminer
    2. PUA threshold: >30% characters in Private Use Area
    3. Font-encoding: subset fonts mapping CJK→ASCII punct

    Args:
        text: The extracted text string.
        chars: Optional list of character dicts with 'text' and 'fontname' keys.
              Required for font-encoding detection (Strategy 3).

    Returns:
        The GarbleStrategy that triggered, or GarbleStrategy.NONE.
    """
    if not text or not text.strip():
        return GarbleStrategy.NONE

    # Strategy 1: CID pattern
    if _CID_PATTERN.search(text):
        return GarbleStrategy.CID

    # Strategy 2: PUA / unmapped characters
    garbled_count = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if is_garbled_char(ch):
            garbled_count += 1
    if total > 0 and garbled_count / total >= GARBLE_PUA_THRESHOLD:
        return GarbleStrategy.PUA

    # Strategy 3: Font-encoding garble (requires character metadata)
    if chars and len(chars) >= GARBLE_MIN_CHARS:
        strategy = _detect_font_encoding_garble(chars)
        if strategy != GarbleStrategy.NONE:
            return strategy

    return GarbleStrategy.NONE


def _detect_font_encoding_garble(page_chars: Sequence[dict]) -> GarbleStrategy:
    """Detect garbled text from broken font encoding mappings.

    Adapted from RAGFlow's `_is_garbled_by_font_encoding`:
    If >30% chars come from subset fonts AND <5% are CJK AND >40% are
    ASCII punctuation, the text is garbled by bad font encoding.
    """
    subset_font_count = 0
    total_non_space = 0
    ascii_punct_sym = 0
    cjk_like = 0

    for c in page_chars:
        text = c.get("text", "")
        fontname = c.get("fontname", "")
        if not text or text.isspace():
            continue
        total_non_space += 1

        if has_subset_font_prefix(fontname):
            subset_font_count += 1

        cp = ord(text[0])
        # CJK Unified Ideographs + extensions + Hangul + Kana
        if (0x2E80 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
                or 0x20000 <= cp <= 0x2FA1F
                or 0xAC00 <= cp <= 0xD7AF
                or 0x3040 <= cp <= 0x30FF):
            cjk_like += 1
        # ASCII punctuation/symbols
        elif (0x21 <= cp <= 0x2F or 0x3A <= cp <= 0x40
                or 0x5B <= cp <= 0x60 or 0x7B <= cp <= 0x7E):
            ascii_punct_sym += 1

    if total_non_space < GARBLE_MIN_CHARS:
        return GarbleStrategy.NONE

    subset_ratio = subset_font_count / total_non_space
    if subset_ratio < GARBLE_SUBSET_FONT_RATIO:
        return GarbleStrategy.NONE

    cjk_ratio = cjk_like / total_non_space
    punct_ratio = ascii_punct_sym / total_non_space
    if cjk_ratio < GARBLE_CJK_RATIO_MAX and punct_ratio > GARBLE_PUNCT_RATIO_MIN:
        return GarbleStrategy.FONT_ENCODING

    return GarbleStrategy.NONE


# ── Page-Level Classification ──────────────────────────────────────────

def classify_page(
    extractable_char_count: int,
    total_visible_area: float,
    page_area: float,
    garble_ratio: float,
) -> PDFType:
    """Classify a single page as text, scanned, or design_tool.

    Args:
        extractable_char_count: Number of characters pdfplumber extracted.
        total_visible_area: Sum of bounding box areas with text.
        page_area: Total page area (width * height).
        garble_ratio: Proportion of text boxes flagged as garbled.
    """
    if extractable_char_count < 10:
        # Almost no extractable text — likely a scanned image
        return PDFType.SCANNED

    if garble_ratio > 0.3:
        # Significant garbled content — design tool (Canva, Figma)
        return PDFType.DESIGN_TOOL

    # Enough clean text — it's a standard text PDF
    return PDFType.TEXT


def classify_document(page_types: list[PDFType]) -> PDFType:
    """Classify the whole document based on per-page classifications."""
    if not page_types:
        return PDFType.SCANNED

    type_counts = {}
    for pt in page_types:
        type_counts[pt] = type_counts.get(pt, 0) + 1

    # If any page is design_tool, the whole doc is design_tool
    if type_counts.get(PDFType.DESIGN_TOOL, 0) > 0:
        return PDFType.DESIGN_TOOL

    # If all pages are scanned
    if type_counts.get(PDFType.SCANNED, 0) == len(page_types):
        return PDFType.SCANNED

    # Mix of text and scanned
    if type_counts.get(PDFType.SCANNED, 0) > 0:
        return PDFType.HYBRID

    return PDFType.TEXT
