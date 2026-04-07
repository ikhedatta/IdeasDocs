"""FastAPI server for knowledge base management.

Endpoints:
- POST   /kb                        — Create knowledge base
- GET    /kb                        — List all KBs
- GET    /kb/{id}                   — Get KB details + doc count
- PUT    /kb/{id}                   — Update KB config
- DELETE /kb/{id}                   — Delete KB + docs + chunks
- GET    /kb/{id}/stats             — KB statistics
- POST   /kb/{id}/documents/upload  — Upload document
- GET    /kb/{id}/documents         — List documents
- GET    /kb/{id}/documents/{doc_id} — Document details
- POST   /kb/{id}/documents/{doc_id}/reprocess — Reprocess document
- DELETE /kb/{id}/documents/{doc_id} — Delete document + chunks
- GET    /health                    — Health check
"""
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from qdrant_client import QdrantClient, models as qdrant_models

from kb_store import KBStore
from models import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    KBCreate,
    KBResponse,
    KBStats,
    KBUpdate,
    ParserConfig,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

store: KBStore | None = None
qdrant: QdrantClient | None = None
upload_dir: Path | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, qdrant, upload_dir
    data_dir = os.getenv("DATA_DIR", "./data")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    store = KBStore(data_dir=data_dir)
    qdrant = QdrantClient(url=qdrant_url)
    upload_dir = Path(data_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"KB manager initialized: data_dir={data_dir}, qdrant={qdrant_url}")
    yield


app = FastAPI(
    title="POC-06: Knowledge Base Manager",
    description="KB lifecycle, document management, parser config, and stats",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kb-manager"}


# --- Knowledge Base Endpoints ---


@app.post("/kb", response_model=KBResponse, status_code=201)
async def create_kb(req: KBCreate):
    """Create a new knowledge base."""
    kb = store.create_kb(
        name=req.name,
        description=req.description,
        parser_config=req.parser_config.model_dump(),
        tags=req.tags,
    )

    # Create Qdrant collection for this KB
    collection_name = f"kb_{kb['id']}"
    try:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": qdrant_models.VectorParams(
                    size=1536, distance=qdrant_models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "bm25": qdrant_models.SparseVectorParams()
            },
        )
        # Create payload indices
        for field in ["document_id", "kb_id", "is_active", "document_name"]:
            qdrant.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )
    except Exception as e:
        logger.warning(f"Collection creation (may already exist): {e}")

    kb["document_count"] = 0
    kb["chunk_count"] = 0
    kb["parser_config"] = ParserConfig(**kb["parser_config"])
    return KBResponse(**kb)


@app.get("/kb", response_model=list[KBResponse])
async def list_kbs():
    """List all knowledge bases."""
    kbs = store.list_kbs()
    results = []
    for kb in kbs:
        kb["chunk_count"] = 0  # Would query Qdrant in production
        kb["parser_config"] = ParserConfig(**kb.get("parser_config", {}))
        results.append(KBResponse(**kb))
    return results


@app.get("/kb/{kb_id}", response_model=KBResponse)
async def get_kb(kb_id: str):
    """Get knowledge base details."""
    kb = store.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    kb["document_count"] = len(store.list_documents(kb_id))
    kb["chunk_count"] = 0
    kb["parser_config"] = ParserConfig(**kb.get("parser_config", {}))
    return KBResponse(**kb)


@app.put("/kb/{kb_id}", response_model=KBResponse)
async def update_kb(kb_id: str, req: KBUpdate):
    """Update knowledge base configuration."""
    updates = req.model_dump(exclude_none=True)
    if "parser_config" in updates and updates["parser_config"]:
        updates["parser_config"] = updates["parser_config"].model_dump() if hasattr(updates["parser_config"], "model_dump") else updates["parser_config"]

    kb = store.update_kb(kb_id, updates)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb["document_count"] = len(store.list_documents(kb_id))
    kb["chunk_count"] = 0
    kb["parser_config"] = ParserConfig(**kb.get("parser_config", {}))
    return KBResponse(**kb)


@app.delete("/kb/{kb_id}")
async def delete_kb(kb_id: str):
    """Delete KB and all its documents and chunks."""
    kb = store.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Delete Qdrant collection
    collection_name = f"kb_{kb_id}"
    try:
        qdrant.delete_collection(collection_name)
    except Exception as e:
        logger.warning(f"Failed to delete collection {collection_name}: {e}")

    # Delete upload files
    kb_upload_dir = upload_dir / kb_id
    if kb_upload_dir.exists():
        shutil.rmtree(kb_upload_dir)

    # Delete metadata
    store.delete_kb(kb_id)

    return {"kb_id": kb_id, "deleted": True}


@app.get("/kb/{kb_id}/stats", response_model=KBStats)
async def get_kb_stats(kb_id: str):
    """Get KB statistics: document count, chunk count, status breakdown."""
    stats = store.get_kb_stats(kb_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KBStats(**stats)


# --- Document Endpoints ---


@app.post("/kb/{kb_id}/documents/upload", response_model=DocumentResponse)
async def upload_document(kb_id: str, file: UploadFile):
    """Upload a document to the KB. Queues for processing."""
    kb = store.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Validate file type
    allowed_types = {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".txt", ".csv"}
    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed_types))}",
        )

    # Save file to upload directory
    kb_upload_dir = upload_dir / kb_id
    kb_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = kb_upload_dir / file.filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Create document record
    doc = store.add_document(
        kb_id=kb_id,
        name=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(content),
    )

    # In production, this would queue a Celery task for processing
    # For POC, just mark as queued
    logger.info(f"Document queued: {file.filename} → KB {kb_id}")

    return DocumentResponse(**doc)


@app.get("/kb/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(kb_id: str):
    """List all documents in a KB."""
    kb = store.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    docs = store.list_documents(kb_id)
    return DocumentListResponse(
        total=len(docs),
        documents=[DocumentResponse(**d) for d in docs],
    )


@app.get("/kb/{kb_id}/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(kb_id: str, doc_id: str):
    """Get document details."""
    doc = store.get_document(doc_id)
    if not doc or doc.get("kb_id") != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**doc)


@app.post("/kb/{kb_id}/documents/{doc_id}/reprocess")
async def reprocess_document(kb_id: str, doc_id: str):
    """Re-queue a document for processing."""
    doc = store.get_document(doc_id)
    if not doc or doc.get("kb_id") != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Reset status to queued
    store.update_document_status(doc_id, DocumentStatus.QUEUED.value, error=None)

    # In production: delete existing chunks from Qdrant, re-queue Celery task
    return {"doc_id": doc_id, "status": "queued", "message": "Document re-queued for processing"}


@app.delete("/kb/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """Delete document and its chunks."""
    doc = store.get_document(doc_id)
    if not doc or doc.get("kb_id") != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete chunks from Qdrant
    collection_name = f"kb_{kb_id}"
    try:
        qdrant.delete(
            collection_name=collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="document_id", match=qdrant_models.MatchValue(value=doc_id)
                        )
                    ]
                )
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to delete chunks for doc {doc_id}: {e}")

    # Delete file
    if doc.get("name"):
        file_path = upload_dir / kb_id / doc["name"]
        if file_path.exists():
            file_path.unlink()

    # Delete metadata
    store.delete_document(doc_id)

    return {"doc_id": doc_id, "deleted": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8006, reload=True)
