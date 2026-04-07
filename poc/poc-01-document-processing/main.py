"""
POC-01: Document Processing Pipeline — Main entry point.

Provides both:
1. CLI tool: python main.py --file document.pdf --kb-id my-kb
2. FastAPI server: uvicorn main:app --reload --port 8001

Demonstrates: Multi-format parsing → token chunking → embedding → Qdrant storage
"""

import os
import sys
import asyncio
import argparse
from uuid import uuid4
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from parsers import ParserRegistry
from chunkers import TokenChunker, ChunkingConfig, ContentBlock
from embedding_service import EmbeddingService
from qdrant_store import QdrantStore
from pipeline import DocumentPipeline


# ============================================
# FastAPI Application
# ============================================

app = FastAPI(
    title="POC-01: Document Processing Pipeline",
    description=(
        "Multi-format document parsing → intelligent chunking → "
        "embedding → Qdrant vector storage. "
        "Adapted from RAGFlow's document processing architecture."
    ),
    version="0.1.0",
)


class ProcessResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    total_blocks: int
    total_chunks: int
    total_tokens: int
    content_hash: str
    errors: list[str]
    chunks_preview: list[dict]


class ChunkPreview(BaseModel):
    id: str
    text_preview: str
    token_count: int
    chunk_order: int
    source_pages: list[int]
    block_types: list[str]


# Global pipeline instance (initialized on startup)
pipeline: Optional[DocumentPipeline] = None


@app.on_event("startup")
async def startup():
    global pipeline
    pipeline = DocumentPipeline(
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
    )


@app.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    kb_id: str = Form(default="default"),
    chunk_token_size: int = Form(default=512),
    chunk_overlap_percent: int = Form(default=10),
    delimiter: str = Form(default="\n"),
):
    """
    Process a document through the full pipeline.
    
    Upload a file → parse → chunk → embed → store in Qdrant.
    Returns chunk count, token count, and preview of created chunks.
    """
    if pipeline is None:
        raise HTTPException(500, "Pipeline not initialized")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "unknown"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    
    if ext not in ParserRegistry.supported_extensions():
        raise HTTPException(
            400,
            f"Unsupported format: {ext}. Supported: {ParserRegistry.supported_extensions()}",
        )

    config = ChunkingConfig(
        chunk_token_size=chunk_token_size,
        chunk_overlap_percent=chunk_overlap_percent,
        delimiter=delimiter,
    )

    doc_id = str(uuid4())
    result = await pipeline.process(
        file_bytes=file_bytes,
        filename=filename,
        kb_id=kb_id,
        document_id=doc_id,
        chunking_config=config,
    )

    if result.errors:
        raise HTTPException(422, detail={"errors": result.errors})

    # Build chunk previews (first 200 chars of each)
    previews = [
        {
            "id": chunk.id,
            "text_preview": chunk.text[:200] + ("..." if len(chunk.text) > 200 else ""),
            "token_count": chunk.token_count,
            "chunk_order": chunk.chunk_order,
            "source_pages": chunk.source_pages,
            "block_types": chunk.block_types,
        }
        for chunk in result.chunks[:20]  # First 20 chunks as preview
    ]

    return ProcessResponse(
        document_id=doc_id,
        filename=filename,
        file_type=result.file_type,
        total_blocks=result.total_blocks,
        total_chunks=result.total_chunks,
        total_tokens=result.total_tokens,
        content_hash=result.content_hash,
        errors=result.errors,
        chunks_preview=previews,
    )


@app.get("/parsers")
async def list_parsers():
    """List all supported file formats."""
    return {"supported_extensions": ParserRegistry.supported_extensions()}


@app.post("/parse-only")
async def parse_only(file: UploadFile = File(...)):
    """
    Parse a document without chunking or embedding.
    Useful for debugging parser output.
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    try:
        parser = ParserRegistry.get(ext)
    except ValueError as e:
        raise HTTPException(400, str(e))

    blocks = parser.parse(file_bytes, filename)

    return {
        "filename": filename,
        "total_blocks": len(blocks),
        "blocks": [
            {
                "text_preview": b.text[:300],
                "block_type": b.block_type.value,
                "page_number": b.page_number,
                "position": b.position,
                "metadata": b.metadata,
            }
            for b in blocks
        ],
    }


@app.post("/chunk-only")
async def chunk_only(
    file: UploadFile = File(...),
    chunk_token_size: int = Form(default=512),
    chunk_overlap_percent: int = Form(default=10),
    delimiter: str = Form(default="\n"),
):
    """
    Parse and chunk a document without embedding.
    Useful for testing different chunking configurations.
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    try:
        parser = ParserRegistry.get(ext)
    except ValueError as e:
        raise HTTPException(400, str(e))

    blocks = parser.parse(file_bytes, filename)
    
    config = ChunkingConfig(
        chunk_token_size=chunk_token_size,
        chunk_overlap_percent=chunk_overlap_percent,
        delimiter=delimiter,
    )
    chunker = TokenChunker(config)
    chunks = chunker.chunk(blocks)

    return {
        "filename": filename,
        "config": {
            "chunk_token_size": chunk_token_size,
            "chunk_overlap_percent": chunk_overlap_percent,
            "delimiter": repr(delimiter),
        },
        "total_blocks": len(blocks),
        "total_chunks": len(chunks),
        "total_tokens": sum(c.token_count for c in chunks),
        "avg_tokens_per_chunk": round(
            sum(c.token_count for c in chunks) / max(len(chunks), 1), 1
        ),
        "chunks": [
            {
                "chunk_order": c.chunk_order,
                "token_count": c.token_count,
                "source_pages": c.source_pages,
                "block_types": c.block_types,
                "text": c.text,
            }
            for c in chunks
        ],
    }


# ============================================
# CLI Entry Point
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="POC-01: Document Processing Pipeline"
    )
    parser.add_argument("--file", "-f", required=True, help="Path to document file")
    parser.add_argument("--kb-id", default="default", help="Knowledge Base ID")
    parser.add_argument("--chunk-size", type=int, default=512, help="Chunk token size")
    parser.add_argument("--overlap", type=int, default=10, help="Overlap percentage")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        help="Embedding model name",
    )
    parser.add_argument("--parse-only", action="store_true", help="Only parse, don't chunk/embed")
    parser.add_argument("--chunk-only", action="store_true", help="Parse and chunk, don't embed")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    with open(args.file, "rb") as f:
        file_bytes = f.read()

    filename = os.path.basename(args.file)
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    print(f"\n{'='*60}")
    print(f"POC-01: Document Processing Pipeline")
    print(f"{'='*60}")
    print(f"File: {filename} ({len(file_bytes):,} bytes)")
    print(f"Format: {ext}")
    print(f"KB ID: {args.kb_id}")

    # === Parse ===
    try:
        doc_parser = ParserRegistry.get(ext)
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    blocks = doc_parser.parse(file_bytes, filename)
    print(f"\nParsed: {len(blocks)} content blocks")
    
    # Show block type breakdown
    type_counts = {}
    for b in blocks:
        t = b.block_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    for btype, count in sorted(type_counts.items()):
        print(f"  {btype}: {count}")

    if args.parse_only:
        print(f"\n--- Parsed Blocks ---")
        for i, b in enumerate(blocks[:10]):
            print(f"\nBlock {i} [{b.block_type.value}] (page {b.page_number}):")
            print(f"  {b.text[:200]}{'...' if len(b.text) > 200 else ''}")
        if len(blocks) > 10:
            print(f"\n... and {len(blocks) - 10} more blocks")
        return

    # === Chunk ===
    config = ChunkingConfig(
        chunk_token_size=args.chunk_size,
        chunk_overlap_percent=args.overlap,
    )
    chunker = TokenChunker(config)
    chunks = chunker.chunk(blocks)

    total_tokens = sum(c.token_count for c in chunks)
    print(f"\nChunked: {len(chunks)} chunks, {total_tokens:,} total tokens")
    print(f"  Avg tokens/chunk: {total_tokens / max(len(chunks), 1):.0f}")
    print(f"  Config: size={args.chunk_size}, overlap={args.overlap}%")

    if args.chunk_only:
        print(f"\n--- Chunks ---")
        for c in chunks[:10]:
            print(f"\nChunk {c.chunk_order} ({c.token_count} tokens, pages {c.source_pages}):")
            print(f"  {c.text[:200]}{'...' if len(c.text) > 200 else ''}")
        if len(chunks) > 10:
            print(f"\n... and {len(chunks) - 10} more chunks")
        return

    # === Embed & Store ===
    print(f"\nEmbedding with: {args.embedding_model}")
    print(f"Storing to Qdrant: {args.qdrant_url}")

    pipeline_instance = DocumentPipeline(
        embedding_model=args.embedding_model,
        qdrant_url=args.qdrant_url,
    )

    result = asyncio.run(
        pipeline_instance.process(
            file_bytes=file_bytes,
            filename=filename,
            kb_id=args.kb_id,
            chunking_config=config,
        )
    )

    if result.errors:
        print(f"\nErrors:")
        for err in result.errors:
            print(f"  ❌ {err}")
    else:
        print(f"\n✅ Success!")
        print(f"  Chunks stored: {result.total_chunks}")
        print(f"  Total tokens: {result.total_tokens:,}")
        print(f"  Collection: kb_{args.kb_id}")
        print(f"  Config hash: {result.content_hash}")


if __name__ == "__main__":
    main()
