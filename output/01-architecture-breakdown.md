# 1. High-Level Architecture Breakdown

## System Components

RAGFlow is organized into 6 major subsystems, each with clear responsibilities:

### 1.1 API Server (`api/`)

**Technology**: Flask/Quart (async Flask) with CORS, JWT auth, OpenAPI schema  
**Entry Point**: `api/ragflow_server.py`

**Blueprint Organization** (22 modules):
- **Core**: `kb_app`, `document_app`, `chunk_app`, `dialog_app`, `canvas_app`
- **Infrastructure**: `llm_app`, `system_app`, `user_app`, `tenant_app`, `api_app`
- **Integrations**: `connector_app`, `mcp_server_app`, `langfuse_app`, `plugin_app`
- **Evaluation**: `evaluation_app`
- **Auth**: `auth/` sub-package (OAuth, password, API tokens)

**Key Design Decisions**:
- Dynamic blueprint discovery via `importlib` — scans `api/apps/` for `*_app.py` files
- 600s response/body timeout (accommodates slow local LLM inference)
- JWT-based auth with API token fallback for external integrations
- Multi-tenant isolation at service layer (most queries filter by `tenant_id`)

### 1.2 Document Processing Pipeline (`rag/flow/`, `deepdoc/`)

**Architecture**: Graph-based component pipeline

```
File → Parser → TokenChunker → Extractor → END
```

- **Parser** (`rag/flow/parser/`): Converts binary files to structured boxes/markdown
  - Delegates to format-specific parsers in `deepdoc/parser/`
  - Uses ONNX neural networks for layout recognition (`deepdoc/vision/`)
  - XGBoost model for intelligent text block merging
- **TokenChunker** (`rag/flow/chunker/`): Splits structured output into semantic chunks
  - Delimiter-based primary splitting
  - Token-budget merging with overlap
  - Table/image context windows
- **Extractor** (`rag/flow/extractor/`): Optional LLM-based field extraction

**Task System**: Redis-backed async queue
- Documents split into tasks (PDFs by page range, Excel by row range)
- xxhash64 digest enables chunk deduplication across re-parses
- Progress tracking with atomic updates, max 3 retries

### 1.3 Retrieval Engine (`rag/nlp/`, `rag/graphrag/`)

**Core Class**: `Dealer` in `rag/nlp/search.py`

**Retrieval Pipeline**:
1. Query tokenization and synonym expansion
2. Parallel keyword (BM25) + vector (cosine) search
3. Weighted fusion (configurable, default 5% keyword + 95% vector)
4. Optional model-based reranking (Jina, BGE, Cohere, etc.)
5. Similarity threshold filtering
6. Token-aware context window construction

**Advanced Features**:
- Knowledge Graph retrieval (`rag/graphrag/search.py`)
- TOC-based section expansion
- Multi-turn query refinement (last 3 messages → single query)
- Cross-language translation before retrieval
- Web search augmentation (Tavily)

### 1.4 LLM Integration (`rag/llm/`)

**Pattern**: Factory-based abstraction with two base classes:
1. `Base` — Direct OpenAI-compatible SDK usage
2. `LiteLLMBase` — Provider abstraction via `litellm` library

**35+ providers** registered via `_FACTORY_NAME` class attribute:
- Direct: OpenAI, Mistral, Google, Baidu, Spark
- LiteLLM: Anthropic, Bedrock, Azure, Groq, DeepSeek, Cohere
- Local: Ollama, HuggingFace, LM-Studio, Xinference, LocalAI

**Model Types**: Chat, Embedding, Reranking, ASR (speech), Image2Text, TTS

### 1.5 Agent Workflow System (`agent/`)

**Architecture**: DSL-based directed graph with typed components

```python
# DSL Structure
{
  "components": {
    "begin": {"obj": {"component_name": "Begin"}, "downstream": ["llm_0"]},
    "llm_0": {"obj": {"component_name": "LLM", "params": {...}}, "downstream": ["retrieval_0"]},
    "retrieval_0": {"obj": {"component_name": "Retrieval"}, "downstream": ["end"]},
  },
  "path": ["begin", "llm_0", "retrieval_0", "end"],
  "globals": {"sys.query": "...", "sys.user_id": "..."}
}
```

**Components**: LLM, Retrieval, Categorize, Switch, Code (Python sandbox), SQL, Web Search, Wikipedia, MCP tools, etc.

### 1.6 Frontend (`web/`)

**Technology**: React + TypeScript + UmiJS + Ant Design + shadcn/ui + Tailwind CSS + Zustand

**Key Pages**:
- Dataset management (KB CRUD, document upload, parser config)
- Chunk explorer (parsed results, chunk results, side-by-side view)
- Chat interface (conversation, source references, sharing)
- Agent canvas (visual workflow builder)
- Document viewer (multi-format preview)

---

## Data Flow Diagrams

### Document Ingestion Flow

```
User uploads file via UI/API
    │
    ▼
document_app.py: validate → store binary in MinIO/S3
    │
    ▼
DocumentService: create Document record (MySQL, status=UNSTART)
    │
    ▼
TaskService.queue_tasks(): split into processing tasks
  ├── PDF: split by page ranges (12 pages/task)
  ├── Excel: split by row ranges (3000 rows/task)
  └── Others: single task
    │
    ▼
Redis Queue: publish unfinished tasks
    │
    ▼
Background Worker picks up task
    │
    ▼
Pipeline.run():
  1. Parser: binary → structured boxes (ONNX layout + OCR)
  2. TokenChunker: boxes → semantic chunks (delimiter + token budget)
  3. Extractor: optional LLM-based metadata extraction
    │
    ▼
For each chunk:
  - Generate embedding vector (embedding model)
  - Extract keywords (NLP tokenizer)
  - Store to Elasticsearch/Infinity (bulk insert, 64 chunks/batch)
  - Store images to MinIO/S3
    │
    ▼
DocumentService: update progress → DONE
KnowledgebaseService: update aggregated counters (chunk_num, token_num)
```

### Chat/Retrieval Flow

```
User sends message via UI/API
    │
    ▼
dialog_app.py → DialogService.async_chat()
    │
    ▼
Load models: embedding, chat, reranker (from TenantLLM config)
    │
    ▼
Query Refinement:
  - Multi-turn: combine last 3 messages into single query
  - Translation: detect language, translate if needed
    │
    ▼
Dealer.retrieval():
  1. Embed query → vector
  2. Tokenize query → BM25 keywords with synonyms
  3. Build FusionExpr: MatchTextExpr + MatchDenseExpr
  4. Execute against selected KB indices
  5. Apply metadata filters
    │
    ▼
Ranking:
  1. Hybrid score = keyword_weight × BM25 + vector_weight × cosine
  2. Optional: model-based reranking (if rerank_id configured)
  3. Filter by similarity_threshold
  4. Optional: GraphRAG augmentation (entity/relation paths)
    │
    ▼
Context Construction (kb_prompt):
  - Format chunks with IDs, titles, URLs, metadata
  - Token-aware truncation (97% of context window)
    │
    ▼
LLM Call:
  - System prompt + citation rules + context + user query
  - Stream response with <think> tag handling
    │
    ▼
Post-processing:
  - Citation extraction and validation
  - Reference aggregation (document IDs, chunk IDs)
  - Return response + references to UI
```

---

## Design Patterns Identified

| Pattern | Where Used | Assessment |
|---------|-----------|------------|
| **Factory Pattern** | LLM provider registration (`_FACTORY_NAME` → class mapping) | Excellent — extensible without code changes |
| **Pipeline/Graph Pattern** | Document processing (File → Parser → Chunker → Extractor → END) | Good — allows reordering, skipping components |
| **Repository Pattern** | `CommonService` base with ORM wrapper methods | Adequate — but Peewee limits async |
| **Strategy Pattern** | Multiple PDF parsers (DeepDOC, MinerU, PaddleOCR, etc.) | Excellent — runtime parser selection |
| **Observer Pattern** | Progress callbacks via Redis pub/sub | Good — real-time status updates |
| **Abstract Factory** | `DocStoreConnection` for ES/Infinity/OceanBase | Good — clean backend switching |
| **Template Method** | Prompt templates with Jinja2 variable injection | Good — separates prompt logic from code |
| **DSL Interpreter** | Agent canvas component graph execution | Over-engineered for most use cases |
| **Multi-tenant Isolation** | `tenant_id` filtering at service layer | Adequate — but no row-level security |
| **Task Queue** | Redis-based async job processing with deduplication | Good — production-proven pattern |
| **Circuit Breaker** | LLM error classification with exponential backoff | Good — handles rate limits gracefully |

---

## Technology Stack Summary

| Layer | RAGFlow Uses | Our Stack | Migration Notes |
|-------|-------------|-----------|-----------------|
| API Framework | Flask/Quart | **FastAPI** | Better async, auto-docs, Pydantic validation |
| ORM | Peewee | **SQLAlchemy** | Better ecosystem, async support |
| Vector Store | Elasticsearch/Infinity | **Qdrant** | Purpose-built, better filtering |
| Object Storage | MinIO | MinIO/S3 | Compatible |
| Task Queue | Redis (custom) | **Celery/Redis** or **Dramatiq** | More robust, better monitoring |
| Frontend | React + UmiJS | **React** | Remove UmiJS dependency |
| State Management | Zustand | Zustand (keep) | Already lightweight |
| Auth | JWT (custom) | **FastAPI Security** | Built-in OAuth2, JWT |
