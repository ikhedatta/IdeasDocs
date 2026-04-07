# 6. What NOT to Copy

## Anti-Patterns and Over-Engineering

---

## 6.1 Peewee ORM with Async Framework

**Problem**: RAGFlow uses Quart (async Flask) but Peewee ORM only supports synchronous database operations. Every DB call blocks the event loop.

**Evidence**: `@DB.connection_context()` decorator on every service method — synchronous connection management in an async application.

**Impact**: Under load, a slow DB query blocks the entire event loop, preventing other requests from being processed. This limits concurrent request handling.

**Our approach**: Use SQLAlchemy with async support (`asyncpg` for PostgreSQL) or Tortoise ORM. FastAPI + async SQLAlchemy is the standard pattern.

---

## 6.2 Custom Task Queue Instead of Celery/Dramatiq

**Problem**: RAGFlow implements its own Redis-based task queue with custom progress tracking, retry logic, and deduplication.

**Evidence**: `api/db/services/task_service.py` — `queue_tasks()` manually publishes to Redis, background threads poll for progress updates, custom retry counting.

**Impact**: No built-in monitoring dashboard, no dead letter queue, no rate limiting, no priority queues, no task result backend. All must be reimplemented.

**Our approach**: Use Celery with Redis broker. Get monitoring (Flower), dead letters, retries, rate limiting, priority, and result backend for free.

---

## 6.3 Magic Number Status Codes

**Problem**: Document status is `run=0` (unstart), `run=1` (running), `run=2` (cancel), `run=3` (done), `run=4` (fail). Generic record status is `status="1"` (active) or `"0"` (deleted).

**Evidence**: Throughout `api/db/db_models.py` and service files — raw integer comparisons without named constants.

**Impact**: No IDE autocomplete, easy to introduce bugs, no type safety.

**Our approach**: Use Python enums:
```python
class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

---

## 6.4 Over-Engineered Agent Canvas System

**Problem**: The DSL-based agent workflow system (`agent/canvas.py`) is a visual programming environment with 20+ component types, conditional branching, loops, and tool integration. It's essentially a no-code AI agent builder.

**Evidence**: 2000+ line `canvas.py`, dozens of component classes in `agent/component/`, complex DSL parsing and execution logic.

**Impact**: Massive surface area to maintain. Most enterprise users need simple sequential chains (retrieve → generate → cite), not a full visual programming environment.

**Our approach**: Start with simple chain patterns:
```python
# Simple sequential pipeline
result = await chain(
    retrieve(query, kb_ids),
    rerank(rerank_model),
    generate(chat_model, prompt_template),
    extract_citations(),
)
```
Add visual workflows only if users demand it. Consider LangGraph for complex flows.

---

## 6.5 Embedding Dimension in Field Names

**Problem**: Vector fields are named `q_768_vec`, `q_1024_vec` based on embedding model dimension. Switching embedding models requires field name changes across the codebase.

**Evidence**: `common/doc_store/doc_store_base.py` — `VECTOR_FIELD_PREFIX = "q_"`, field name construction includes dimension.

**Impact**: Tight coupling between embedding model choice and storage schema. Migration between models is painful.

**Our approach**: Qdrant uses collection-level vector configuration. Name vectors semantically (`dense`, `sparse`) not by dimension.

---

## 6.6 Monolithic Dialog Service

**Problem**: `dialog_service.py` handles: chat orchestration, model loading, query refinement, retrieval, reranking, context construction, LLM calling, streaming, citation extraction, error handling, multi-turn management, web search, GraphRAG integration — all in one file.

**Impact**: Hard to test, hard to modify, hard to understand. A change to citation logic risks breaking streaming.

**Our approach**: Decompose into focused services (see Section 5.2 of engineering insights).

---

## 6.7 Blueprint Auto-Discovery via importlib

**Problem**: RAGFlow dynamically discovers and registers Flask blueprints by scanning directories with `importlib`.

**Evidence**: `api/apps/__init__.py` — glob patterns find `*_app.py` files and register them.

**Impact**: Implicit registration makes it hard to understand what endpoints exist. A malformed Python file in the directory can break the entire server at startup.

**Our approach**: Explicit router registration in FastAPI:
```python
from fastapi import FastAPI
from .routers import knowledge_base, documents, chunks, chat

app = FastAPI()
app.include_router(knowledge_base.router, prefix="/api/v1/kb")
app.include_router(documents.router, prefix="/api/v1/documents")
```

---

## 6.8 600-Second Timeout Defaults

**Problem**: Both `RESPONSE_TIMEOUT` and `BODY_TIMEOUT` are set to 600 seconds to accommodate slow local LLM inference (Ollama).

**Evidence**: `api/apps/__init__.py` — `RESPONSE_TIMEOUT = 600`, `BODY_TIMEOUT = 600`.

**Impact**: A stuck request holds a connection for 10 minutes. Under load, this exhausts connection pools.

**Our approach**: Use streaming for LLM responses (FastAPI StreamingResponse). Set reasonable timeouts (30s for non-streaming, SSE for long-running generation). Never wait 10 minutes for a synchronous response.

---

## 6.9 Mixed Authentication Mechanisms

**Problem**: RAGFlow supports JWT tokens, API tokens, session cookies, and multiple OAuth providers in a single middleware chain. The `_load_user()` function tries JWT first, then API token, then session.

**Impact**: Complex security surface. Easy to introduce auth bypass bugs.

**Our approach**: Pick ONE primary auth mechanism (JWT via FastAPI Security), add API key support for machine-to-machine only. Use a standard OAuth library (authlib) for SSO.

---

## 6.10 Frontend UmiJS Dependency

**Problem**: UmiJS is a Chinese-ecosystem React framework with its own routing, build tooling, and conventions. It adds complexity without proportional benefit for international teams.

**Impact**: Smaller talent pool, less documentation in English, harder to debug.

**Our approach**: Standard React + Vite + React Router. Use Zustand for state (RAGFlow already uses this — keep it).

---

## 6.11 Things That Are Fine But Not for Our Scale

| Feature | In RAGFlow | Skip Because |
|---------|-----------|--------------|
| OceanBase support | Full SQL-compatible vector store | We have Qdrant — don't need a 3rd vector backend |
| MCP Server integration | Model Context Protocol for tool sharing | Premature for initial build — add later |
| Plugin system | Dynamic plugin loading | YAGNI — hardcode integrations first |
| GCS/Azure/OSS storage | 5+ storage backends | MinIO/S3 covers 99% of cases |
| Multiple database engines | MySQL + PostgreSQL + OceanBase | Pick PostgreSQL, use only that |
| Canvas templates | Pre-built agent workflows | Build specific chains, not a template system |

---

## Summary: Copy vs Skip Decision Matrix

| Feature | Copy? | Effort | Impact |
|---------|-------|--------|--------|
| Deep document parsing approach | ✅ Yes | High | Critical |
| Hybrid search with fusion weights | ✅ Yes | Medium | Critical |
| Chunk CRUD with toggle | ✅ Yes | Low | High |
| Citation enforcement prompts | ✅ Yes | Low | Critical |
| Multi-format parser registry | ✅ Yes | Medium | High |
| Task-based async processing | ✅ Celery instead | Medium | High |
| LLM provider abstraction | ✅ litellm instead | Low | Medium |
| GraphRAG | ⚠️ Phase 3 | High | Medium |
| Retrieval test endpoint | ✅ Yes | Low | High |
| Per-tenant LLM config | ⚠️ Phase 2 | Medium | Medium |
| Auto keyword/question gen | ⚠️ Phase 2 | Medium | Medium |
| Peewee ORM | ❌ No | — | — |
| Custom task queue | ❌ No | — | — |
| Agent canvas/DSL system | ❌ No | — | — |
| UmiJS frontend | ❌ No | — | — |
| Blueprint auto-discovery | ❌ No | — | — |
| 600s timeouts | ❌ No | — | — |
