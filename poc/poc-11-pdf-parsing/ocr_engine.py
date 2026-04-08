"""OCR engine for fallback text extraction.

Phase 1b: When text extraction produces garbled output (detected by
classifier.py), this module OCRs the specific garbled regions.

Design:
- BaseOCREngine is an abstract interface — swap implementations freely
- TesseractOCREngine is the POC default (pip-installable, no GPU)
- Production should use PaddleOCR or a cloud OCR API

RAGFlow uses PaddleOCR with GPU-parallel processing across devices.
This POC uses Tesseract for simplicity but the interface is identical.
"""

from __future__ import annotations

import abc
import logging
from typing import Optional

import numpy as np
from PIL import Image

from config import (
    OCR_CONFIDENCE_THRESHOLD,
    PAGE_ZOOM,
    TESSERACT_CMD,
    TESSERACT_LANG,
)
from models import BoundingBox, TextBox

logger = logging.getLogger(__name__)


class BaseOCREngine(abc.ABC):
    """Abstract OCR engine interface.

    Implement this to swap Tesseract for PaddleOCR, Google Vision, etc.
    """

    @abc.abstractmethod
    def ocr_region(
        self,
        page_image: Image.Image,
        bbox: BoundingBox,
    ) -> str:
        """OCR a specific rectangular region of a page image.

        Args:
            page_image: Full page rendered at PAGE_DPI.
            bbox: Bounding box in page coordinates (72 DPI base).

        Returns:
            Extracted text for the region.
        """

    @abc.abstractmethod
    def ocr_full_page(
        self,
        page_image: Image.Image,
    ) -> list[dict]:
        """OCR an entire page image.

        Returns:
            List of dicts: [{"text": str, "bbox": (x0,y0,x1,y1), "confidence": float}]
            Coordinates are in page-coordinate space (72 DPI base).
        """

    def fill_garbled_boxes(
        self,
        text_boxes: list[TextBox],
        page_image: Optional[Image.Image],
    ) -> tuple[list[TextBox], int]:
        """Fill garbled/empty text boxes with OCR results.

        Args:
            text_boxes: Text boxes from Phase 1 (some with empty text).
            page_image: Page image for OCR (None if not needed).

        Returns:
            (updated_text_boxes, ocr_count)
        """
        if page_image is None:
            return text_boxes, 0

        ocr_count = 0
        for box in text_boxes:
            if box.source == "ocr_pending" or (not box.text.strip()):
                ocr_text = self.ocr_region(page_image, box.bbox)
                if ocr_text.strip():
                    box.text = ocr_text.strip()
                    box.source = "ocr"
                    box.confidence = 0.8  # Indicate OCR confidence
                    ocr_count += 1
                    logger.debug(
                        "OCR resolved box at (%.1f, %.1f): '%s'",
                        box.bbox.x0, box.bbox.y0, ocr_text[:50],
                    )

        # Also OCR the full page to find regions pdfplumber missed entirely
        if not text_boxes or all(not b.text.strip() for b in text_boxes):
            full_results = self.ocr_full_page(page_image)
            for result in full_results:
                if result["confidence"] >= OCR_CONFIDENCE_THRESHOLD:
                    # Convert back to page coordinates
                    rx0, ry0, rx1, ry1 = result["bbox"]
                    text_boxes.append(TextBox(
                        text=result["text"],
                        bbox=BoundingBox(
                            x0=rx0, y0=ry0, x1=rx1, y1=ry1,
                            page=text_boxes[0].bbox.page if text_boxes else 0,
                        ),
                        source="ocr",
                        confidence=result["confidence"],
                    ))
                    ocr_count += 1

        return text_boxes, ocr_count


class TesseractOCREngine(BaseOCREngine):
    """Tesseract-based OCR engine (CPU, pip-installable).

    Production replacement: PaddleOCR with GPU for 5-10x speedup.
    """

    def __init__(self):
        try:
            import pytesseract
            if TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            self._pytesseract = pytesseract
            # Verify tesseract is available
            pytesseract.get_tesseract_version()
            self._available = True
            logger.info("Tesseract OCR initialized (lang=%s)", TESSERACT_LANG)
        except Exception as e:
            logger.warning("Tesseract not available: %s. OCR will be skipped.", e)
            self._pytesseract = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def ocr_region(self, page_image: Image.Image, bbox: BoundingBox) -> str:
        """Crop the bbox region from page image and OCR it."""
        if not self._available:
            return ""

        # Convert page coords (72 DPI) to image coords (PAGE_DPI)
        crop_box = (
            int(bbox.x0 * PAGE_ZOOM),
            int(bbox.y0 * PAGE_ZOOM),
            int(bbox.x1 * PAGE_ZOOM),
            int(bbox.y1 * PAGE_ZOOM),
        )

        # Clamp to image bounds
        iw, ih = page_image.size
        crop_box = (
            max(0, crop_box[0]),
            max(0, crop_box[1]),
            min(iw, crop_box[2]),
            min(ih, crop_box[3]),
        )

        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            return ""

        region = page_image.crop(crop_box)

        # Upscale small regions for better OCR
        rw, rh = region.size
        if rw < 100 or rh < 30:
            scale = max(100 / max(rw, 1), 30 / max(rh, 1), 1.0)
            scale = min(scale, 4.0)  # Cap at 4x
            region = region.resize(
                (int(rw * scale), int(rh * scale)),
                Image.LANCZOS,
            )

        try:
            text = self._pytesseract.image_to_string(
                region,
                lang=TESSERACT_LANG,
                config="--psm 6",  # Assume uniform block of text
            )
            return text.strip()
        except Exception as e:
            logger.warning("Tesseract OCR failed for region: %s", e)
            return ""

    def ocr_full_page(self, page_image: Image.Image) -> list[dict]:
        """OCR the full page and return boxes with text + confidence."""
        if not self._available:
            return []

        try:
            data = self._pytesseract.image_to_data(
                page_image,
                lang=TESSERACT_LANG,
                config="--psm 3",  # Fully automatic page segmentation
                output_type=self._pytesseract.Output.DICT,
            )
        except Exception as e:
            logger.warning("Tesseract full-page OCR failed: %s", e)
            return []

        results = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not text or conf < 0:
                continue

            confidence = conf / 100.0
            if confidence < OCR_CONFIDENCE_THRESHOLD:
                continue

            # Convert from image coords back to page coords
            x = data["left"][i] / PAGE_ZOOM
            y = data["top"][i] / PAGE_ZOOM
            w = data["width"][i] / PAGE_ZOOM
            h = data["height"][i] / PAGE_ZOOM

            results.append({
                "text": text,
                "bbox": (x, y, x + w, y + h),
                "confidence": confidence,
            })

        return results


class NoOpOCREngine(BaseOCREngine):
    """No-op OCR engine for testing or when OCR is not available."""

    def ocr_region(self, page_image: Image.Image, bbox: BoundingBox) -> str:
        return ""

    def ocr_full_page(self, page_image: Image.Image) -> list[dict]:
        return []
