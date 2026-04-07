# POC-04: Chunk Management API

## Feature
**Full CRUD for chunks with toggle, edit, re-embed, and manual creation**

In enterprise RAG, chunks aren't fire-and-forget. Subject matter experts need to review, correct, disable, and manually inject chunks. This POC implements RAGFlow's chunk management from `api/apps/chunk_app.py`.

## What Problem It Solves
- **Bad chunks exist**: Auto-parsing sometimes produces garbage. Users need to disable them without re-processing
- **Expert knowledge gaps**: Some information only exists in people's heads. Manual chunk injection closes gaps
- **Chunk editing**: OCR errors, table parsing mistakes — users need to fix content and re-embed
- **Soft delete**: Audit trails require soft delete (toggle off) rather than permanent removal
- **Bulk operations**: Processing hundreds of chunks one-by-one is impractical

## Key RAGFlow Patterns Implemented
- **`available_int` toggle** (`chunk_app.py` — `switch()`) — enable/disable chunks without deleting
- **Re-embedding on edit** (`chunk_app.py` — `set()`) — when content changes, re-compute vectors
- **Manual chunk creation** (`chunk_app.py` — `create()`) — inject knowledge directly
- **Chunk search within KB** (`chunk_app.py` — `list()`) — filter by document, status, keyword
- **Batch operations** — toggle/delete multiple chunks at once

## Architecture

```
FastAPI CRUD Endpoints
    │
    ├── GET    /chunks?kb_id=...&doc_id=...&q=...&status=active
    ├── GET    /chunks/{id}
    ├── POST   /chunks              (manual creation + auto-embed)
    ├── PUT    /chunks/{id}         (edit content → re-embed)
    ├── PATCH  /chunks/{id}/toggle  (soft enable/disable)
    ├── DELETE /chunks/{id}         (hard delete)
    └── POST   /chunks/batch        (bulk toggle/delete)
    │
    ▼
Qdrant Vector Store
    ├── Upsert (create/update with new vectors)
    ├── Payload update (toggle is_active flag)
    ├── Delete points
    └── Scroll/search with filters
    │
    ▼
litellm Embedding Service
    └── Re-embed when content changes
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server with full CRUD endpoints |
| `chunk_store.py` | Qdrant operations for chunk CRUD |
| `embedding_service.py` | Embed/re-embed chunks via litellm |
| `models.py` | Pydantic models for request/response |

## How to Run

```bash
# Prerequisites: Qdrant running + documents indexed via POC-01
export OPENAI_API_KEY="sk-..."

uvicorn main:app --reload --port 8004

# List chunks: GET /chunks?kb_id=my-kb&status=active
# Create:      POST /chunks {"kb_id": "my-kb", "content": "...", "document_name": "manual"}
# Edit:        PUT /chunks/{id} {"content": "updated text"}
# Toggle:      PATCH /chunks/{id}/toggle {"is_active": false}
# Batch:       POST /chunks/batch {"chunk_ids": [...], "action": "disable"}
```

## How to Extend

1. **Versioning**: Track chunk edit history for audit
2. **Approval workflow**: Chunks need review before going live
3. **Metadata schemas**: Custom fields per KB (e.g., department, classification)
4. **Import/export**: Bulk upload chunks from CSV/JSON
5. **Wire to POC-01**: Use document processing pipeline, manage results here
