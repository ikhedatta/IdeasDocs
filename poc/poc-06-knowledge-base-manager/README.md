# POC-06: Knowledge Base Manager

## Feature
**KB lifecycle CRUD, document management, parser configuration, and statistics**

This is the management layer that ties everything together. It manages knowledge bases (collections of documents), tracks document processing status, and provides the admin interface patterns from RAGFlow's `kb_app.py` and `document_app.py`.

## What Problem It Solves
- **Multi-tenant KB isolation**: Different teams need separate knowledge bases
- **Document lifecycle**: Upload → parse → chunk → embed → ready (with status tracking)
- **Parser configuration**: Different document types need different parsing strategies
- **KB statistics**: How many docs, chunks, tokens in each KB? What's the processing status?
- **Soft delete and cleanup**: Delete a KB and all its chunks/documents

## Key RAGFlow Patterns Implemented
- **KB CRUD** (`api/apps/kb_app.py` — create, list, update, delete)
- **Document management** (`api/apps/document_app.py` — upload, status, reprocess)
- **Parser config per KB** (each KB stores its parser settings)
- **Status tracking** (document states: queued → parsing → chunking → embedding → ready → error)
- **KB statistics aggregation** (doc count, chunk count, active chunks, token budget)

## Architecture

```
FastAPI Endpoints
    │
    ├── Knowledge Bases (/kb)
    │   ├── POST   /kb              — Create KB
    │   ├── GET    /kb              — List KBs
    │   ├── GET    /kb/{id}         — Get KB with stats
    │   ├── PUT    /kb/{id}         — Update KB config
    │   └── DELETE /kb/{id}         — Delete KB + all docs/chunks
    │
    ├── Documents (/kb/{id}/documents)
    │   ├── POST   /kb/{id}/documents/upload   — Upload + queue processing
    │   ├── GET    /kb/{id}/documents           — List documents with status
    │   ├── GET    /kb/{id}/documents/{doc_id}  — Document details
    │   ├── POST   /kb/{id}/documents/{doc_id}/reprocess — Re-parse
    │   └── DELETE /kb/{id}/documents/{doc_id}  — Delete doc + its chunks
    │
    └── Stats
        └── GET    /kb/{id}/stats    — Chunk count, token count, doc status
    │
    ▼
PostgreSQL (metadata) + Qdrant (vectors)
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server with KB and document endpoints |
| `kb_store.py` | KB metadata storage (JSON file-based for POC) |
| `document_tracker.py` | Document status tracking |
| `models.py` | Pydantic request/response models |

## How to Run

```bash
export OPENAI_API_KEY="sk-..."

uvicorn main:app --reload --port 8006

# Create KB:  POST /kb {"name": "Company Policies", "description": "HR and safety policies"}
# List KBs:   GET /kb
# KB stats:   GET /kb/{id}/stats
# Upload doc: POST /kb/{id}/documents/upload (multipart form)
```

## How to Extend

1. **PostgreSQL/SQLAlchemy**: Replace JSON store with proper DB (models ready for migration)
2. **Celery task queue**: Queue document processing as async tasks
3. **Parser config UI**: Frontend for configuring chunking strategy per KB
4. **Permission system**: Role-based access to KBs (admin/editor/viewer)
5. **Wire to other POCs**: Use POC-01 for processing, POC-04 for chunk management
