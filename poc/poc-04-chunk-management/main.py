"""FastAPI server for chunk management CRUD.

Endpoints:
- GET    /chunks             — List/search chunks with filters
- GET    /chunks/{chunk_id}  — Get single chunk
- POST   /chunks             — Create manual chunk (auto-embeds)
- PUT    /chunks/{chunk_id}  — Update content (re-embeds)
- PATCH  /chunks/{chunk_id}/toggle — Toggle active/inactive
- DELETE /chunks/{chunk_id}  — Hard delete
- POST   /chunks/batch       — Bulk toggle or delete
- GET    /health             — Health check
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from chunk_store import ChunkStore
from embedding_service import EmbeddingService
from models import (
    BatchAction,
    BatchRequest,
    BatchResponse,
    ChunkCreate,
    ChunkListResponse,
    ChunkResponse,
    ChunkToggle,
    ChunkUpdate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

store: ChunkStore | None = None
embedder: EmbeddingService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, embedder
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    store = ChunkStore(qdrant_url=qdrant_url)
    embedder = EmbeddingService(model=embedding_model)
    logger.info(f"Chunk management API initialized: qdrant={qdrant_url}")
    yield


app = FastAPI(
    title="POC-04: Chunk Management API",
    description="Full CRUD for chunks with toggle, edit, re-embed, and manual creation",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "chunk-management"}


@app.get("/chunks", response_model=ChunkListResponse)
async def list_chunks(
    kb_id: str = Query(..., description="Knowledge base ID"),
    document_id: str | None = Query(None, description="Filter by document ID"),
    status: str = Query("all", description="Filter: active, inactive, or all"),
    keyword: str | None = Query(None, description="Text search within chunk content"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List chunks with optional filtering and pagination."""
    chunks, total = store.list_chunks(
        kb_id=kb_id,
        document_id=document_id,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )

    return ChunkListResponse(
        total=total,
        page=page,
        page_size=page_size,
        chunks=[ChunkResponse(**c) for c in chunks],
    )


@app.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: str, kb_id: str = Query(...)):
    """Get a single chunk by ID."""
    chunk = store.get_chunk(kb_id, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return ChunkResponse(**chunk)


@app.post("/chunks", response_model=ChunkResponse, status_code=201)
async def create_chunk(req: ChunkCreate):
    """Create a manual chunk. Automatically generates embedding."""
    # Embed the content
    vector = await embedder.embed(req.content)

    chunk_id = store.create_chunk(
        kb_id=req.kb_id,
        content=req.content,
        vector=vector,
        document_id=req.document_id,
        document_name=req.document_name,
        metadata=req.metadata,
    )

    # Fetch and return the created chunk
    chunk = store.get_chunk(req.kb_id, chunk_id)
    if not chunk:
        raise HTTPException(status_code=500, detail="Failed to retrieve created chunk")
    return ChunkResponse(**chunk)


@app.put("/chunks/{chunk_id}", response_model=ChunkResponse)
async def update_chunk(chunk_id: str, req: ChunkUpdate, kb_id: str = Query(...)):
    """Update chunk content. Re-embeds automatically."""
    # Re-embed the updated content
    vector = await embedder.embed(req.content)

    success = store.update_chunk(
        kb_id=kb_id,
        chunk_id=chunk_id,
        content=req.content,
        vector=vector,
        metadata=req.metadata,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Chunk not found")

    chunk = store.get_chunk(kb_id, chunk_id)
    return ChunkResponse(**chunk)


@app.patch("/chunks/{chunk_id}/toggle", response_model=dict)
async def toggle_chunk(chunk_id: str, req: ChunkToggle, kb_id: str = Query(...)):
    """Toggle chunk active/inactive without re-embedding."""
    success = store.toggle_chunk(kb_id, chunk_id, req.is_active)
    if not success:
        raise HTTPException(status_code=404, detail="Chunk not found or toggle failed")
    return {
        "chunk_id": chunk_id,
        "is_active": req.is_active,
        "message": f"Chunk {'enabled' if req.is_active else 'disabled'}",
    }


@app.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str, kb_id: str = Query(...)):
    """Hard delete a chunk from the vector store."""
    success = store.delete_chunk(kb_id, chunk_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chunk not found or delete failed")
    return {"chunk_id": chunk_id, "deleted": True}


@app.post("/chunks/batch", response_model=BatchResponse)
async def batch_operation(req: BatchRequest):
    """Bulk toggle or delete multiple chunks."""
    if req.action == BatchAction.ENABLE:
        succeeded, errors = store.batch_toggle(req.kb_id, req.chunk_ids, is_active=True)
    elif req.action == BatchAction.DISABLE:
        succeeded, errors = store.batch_toggle(req.kb_id, req.chunk_ids, is_active=False)
    elif req.action == BatchAction.DELETE:
        succeeded, errors = store.batch_delete(req.kb_id, req.chunk_ids)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    return BatchResponse(
        action=req.action.value,
        total=len(req.chunk_ids),
        succeeded=succeeded,
        failed=len(req.chunk_ids) - succeeded,
        errors=errors,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)
