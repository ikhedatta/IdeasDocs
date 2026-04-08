# RAGFlow-Inspired POC Collection

## Purpose
These Proof-of-Concept implementations extract the **most valuable patterns** from RAGFlow's architecture and implement them as standalone, runnable modules. Each POC is designed to be picked up by an LLM or developer to build a full-fledged enterprise RAG platform.

## Target Stack
- **Python 3.11+**
- **FastAPI** (async API framework)
- **Qdrant** (vector database — dense + sparse hybrid search)
- **PostgreSQL** (metadata storage)
- **litellm** (multi-provider LLM abstraction)
- **Celery + Redis** (async task processing)
- **MinIO/S3** (object storage)
- **React** (frontend — see POC-07 and POC-08 for Next.js UI implementations)

## POC Index

| POC | Feature | Description | Key RAGFlow Insight |
|-----|---------|-------------|---------------------|
| [poc-01](poc-01-document-processing/) | **Document Processing Pipeline** | Parse PDF/DOCX/HTML/MD → chunk → embed → store | Multi-format parsing, token-based chunking with overlap, layout awareness |
| [poc-02](poc-02-hybrid-retrieval/) | **Hybrid Retrieval Engine** | Dense + sparse vector search with configurable fusion | Weighted BM25+vector fusion, RRF, threshold filtering |
| [poc-03](poc-03-citation-rag/) | **Citation-Enforced RAG** | Full RAG pipeline with mandatory citations | Citation prompt engineering, reference tracking, hallucination prevention |
| [poc-04](poc-04-chunk-management/) | **Chunk Management API** | CRUD for chunks with toggle, edit, re-embed | Human-in-the-loop QA, soft disable, inline editing |
| [poc-05](poc-05-retrieval-debugger/) | **Retrieval Debugger** | Test retrieval, compare configs, analyze scores | Score decomposition, latency timing, A/B comparison |
| [poc-06](poc-06-knowledge-base-manager/) | **Knowledge Base Manager** | KB lifecycle: create → upload → parse → manage → search | Metadata schema, tag management, parser config |
| [poc-07](poc-07-visual-kb-management/) | **Visual KB Management UI** | Next.js UI for chunk-level visibility, inspection, toggle, editing | KB dashboard, chunk explorer, inline editor, status badges |
| [poc-08](poc-08-retrieval-debugger-ui/) | **Retrieval Debugger UI** | Next.js UI for retrieval testing, score visualization, A/B comparison | Score bars, timing breakdown, overlap analysis, batch test runner |
| [poc-09](poc-09-data-source-connectors/) | **Data Source Connectors** | Connector framework for 13 external sources with sync orchestration | Factory+registry pattern, mixin interfaces, encrypted creds, checkpoint sync |
| [poc-10](poc-10-data-source-ui/) | **Data Source Management UI** | Next.js UI for connector catalog, connect wizard, sync dashboard, content browser | Source catalog grid, 3-step wizard, sync timeline, tree browser |
| [poc-11](poc-11-pdf-parsing/) | **PDF Parsing Pipeline** | Efficient PDF text extraction with garble detection, OCR fallback, layout analysis, chunking | 3-strategy garble detection (PUA/CID/font-encoding), dual-library extraction, K-Means column detection |

### Frontend POCs (Next.js)
| POC | Port | Backend Dependency |
|-----|------|--------------------|
| poc-07 | 3000 | POC-04 (:8004) + POC-06 (:8006) |
| poc-08 | 3001 | POC-05 (:8005) |
| poc-10 | 3002 | POC-09 (:8009) |

## How to Use These POCs

### Prerequisites
```bash
# 1. Start Qdrant (Docker)
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export OPENAI_API_KEY="your-key-here"
# OR for local models:
export LLM_BASE_URL="http://localhost:11434"
export LLM_MODEL="ollama/llama3"
export EMBEDDING_MODEL="ollama/nomic-embed-text"
```

### Running Individual POCs
Each POC has its own README with specific instructions. Generally:
```bash
cd poc-01-document-processing
python main.py          # Run standalone demo
# OR
uvicorn main:app --reload  # For API-based POCs
```

## Architecture Target

These POCs are building blocks for this target architecture:

```
┌─────────────────────────────────────────────────────────────┐
│              React / Next.js Frontend                       │
│   KB Dashboard (POC-07) │ Retrieval Debugger (POC-08)       │
│   Chunk Explorer │ Inline Editor │ A/B Compare │ Batch Test │
│   Data Source UI (POC-10) │ Source Catalog │ Connect Wizard  │
└────────────────────────────┬────────────────────────────────┘
                             │ REST API
┌────────────────────────────▼────────────────────────────────┐
│              FastAPI Server (POC-04, POC-06, POC-09)         │
│   /api/v1/kb │ /api/v1/documents │ /api/v1/chunks │ /chat  │
│   /connectors │ /sources │ /connectors/{id}/sync            │
├─────────────────────────────────────────────────────────────┤
│              Service Layer                                  │
│  DocumentService │ ChunkService │ RetrievalService │ ChatSvc│
│       (POC-01)       (POC-04)       (POC-02)     (POC-03)  │
│  ConnectorRegistry │ SyncEngine (POC-09)                    │
├──────────┬──────────┬────────────┬──────────────────────────┤
│PostgreSQL│  Redis   │  MinIO/S3  │        Qdrant            │
│ (metadata│ (tasks)  │  (files)   │ (vectors + payloads)     │
└──────────┴──────────┴────────────┴──────────────────────────┘
  ▲ External Sources (13): S3, Confluence, Discord, Google Drive,
    Gmail, Jira, Dropbox, GCS, GitLab, GitHub, Bitbucket,
    Zendesk, Asana → POC-09 connectors → POC-01 pipeline
```

## Integration Path

1. **Start with POC-01** — Get document ingestion working
2. **Add POC-02** — Wire up hybrid search
3. **Combine with POC-03** — Complete RAG pipeline with citations
4. **Layer POC-04** — Add chunk management for quality control
5. **Add POC-05** — Retrieval debugging for optimization
6. **Wrap with POC-06** — Full KB lifecycle management
7. **Connect POC-07** — Visual KB management UI (Next.js on :3000)
8. **Connect POC-08** — Retrieval debugger UI (Next.js on :3001)
9. **Add POC-09** — Data source connectors for 13 external sources (FastAPI on :8009)
10. **Connect POC-10** — Data source management UI (Next.js on :3002)

Each POC is self-contained but shares the same data models and Qdrant schema, making integration straightforward.
