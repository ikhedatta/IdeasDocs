"""POC-11 — PDF Parsing Pipeline API.

FastAPI endpoint for uploading PDFs and getting parsed chunks.
"""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import MAX_FILE_SIZE_MB
from models import ParseResponse
from pipeline import PDFParsingPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="POC-11 · Efficient PDF Parsing Pipeline",
    description="Parse PDFs (including Canva-generated) with garble detection, OCR fallback, layout analysis, and semantic chunking.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize pipeline once
pipeline = PDFParsingPipeline()


@app.post("/parse", response_model=ParseResponse)
async def parse_pdf(
    file: UploadFile = File(...),
    chunk_size: int = Query(512, ge=64, le=4096, description="Max tokens per chunk"),
    chunk_overlap: int = Query(64, ge=0, le=512, description="Overlap tokens between chunks"),
):
    """Upload and parse a PDF file.

    Returns structured chunks with position metadata, ready for embedding.
    Handles Canva-generated PDFs with automatic OCR fallback for garbled text.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    # Read and validate size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(413, f"File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)")

    # Write to temp file (pdfplumber/fitz need a file path)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = pipeline.parse(
            pdf_path=tmp_path,
            filename=file.filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            skip_embedding=True,  # Embedding is a separate step in production
        )

        doc = result["document"]
        chunks = result["chunks"]

        return ParseResponse(
            document_id=doc.id,
            filename=doc.filename,
            pdf_type=doc.pdf_type.value,
            page_count=doc.page_count,
            chunk_count=len(chunks),
            total_text_boxes=doc.total_text_boxes,
            garbled_boxes_detected=doc.total_garbled_boxes,
            ocr_boxes_used=doc.total_ocr_boxes,
            processing_time_ms=doc.processing_time_ms,
            chunks=chunks,
        )

    except Exception as e:
        logger.exception("Failed to parse PDF: %s", e)
        raise HTTPException(500, f"Parse failed: {e}")

    finally:
        os.unlink(tmp_path)


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "ocr_available": isinstance(pipeline.ocr_engine, __import__("ocr_engine").TesseractOCREngine)
                         and pipeline.ocr_engine.available,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
