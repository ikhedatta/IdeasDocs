"""Configuration constants for the PDF parsing pipeline.

Thresholds are derived from RAGFlow's battle-tested defaults
(deepdoc/parser/pdf_parser.py) with adjustments for this POC's
Tesseract-based OCR path.
"""

from __future__ import annotations

import os

# ── Rendering ──────────────────────────────────────────────────────────
PAGE_DPI = int(os.getenv("PAGE_DPI", "300"))
PAGE_ZOOM = PAGE_DPI / 72  # pdfplumber default is 72 DPI

# ── Garble Detection (RAGFlow thresholds) ──────────────────────────────
GARBLE_PUA_THRESHOLD = float(os.getenv("GARBLE_PUA_THRESHOLD", "0.3"))
GARBLE_SUBSET_FONT_RATIO = float(os.getenv("GARBLE_SUBSET_FONT_RATIO", "0.3"))
GARBLE_CJK_RATIO_MAX = float(os.getenv("GARBLE_CJK_RATIO_MAX", "0.05"))
GARBLE_PUNCT_RATIO_MIN = float(os.getenv("GARBLE_PUNCT_RATIO_MIN", "0.4"))
GARBLE_MIN_CHARS = int(os.getenv("GARBLE_MIN_CHARS", "5"))

# ── OCR ────────────────────────────────────────────────────────────────
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.5"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")  # blank = use default path
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "eng")  # e.g. "eng+hin+tam"
OCR_WORKERS = int(os.getenv("OCR_WORKERS", "4"))

# ── Layout Heuristics ─────────────────────────────────────────────────
TITLE_MIN_FONT_RATIO = float(os.getenv("TITLE_MIN_FONT_RATIO", "1.3"))
HEADER_FOOTER_MARGIN = float(os.getenv("HEADER_FOOTER_MARGIN", "0.05"))
COLUMN_SILHOUETTE_THRESHOLD = float(os.getenv("COLUMN_SILHOUETTE_THRESHOLD", "0.4"))

# ── Chunking ──────────────────────────────────────────────────────────
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "512"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "64"))
CHUNK_DELIMITERS = os.getenv("CHUNK_DELIMITERS", r"\n|\.(?=\s)|[!?;]")

# ── Parallelism ───────────────────────────────────────────────────────
MAX_PAGES_PARALLEL = int(os.getenv("MAX_PAGES_PARALLEL", "4"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
