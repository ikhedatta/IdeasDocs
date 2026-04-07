# 7. Adaptation Roadmap

## Step-by-Step Execution Plan

Based on deep analysis of RAGFlow's architecture, here's a phased plan to build an enterprise-grade, controlled RAG platform. Prioritized by **impact-to-effort ratio** with our stack: Python, FastAPI, Qdrant, React, Docker.

---

## Phase 1: Foundation (Quick Wins — High Impact, Low-Medium Effort)

### Milestone: "Working RAG with citations and chunk visibility"

#### 1.1 Core Data Models & API Skeleton

**What**: PostgreSQL schema + FastAPI routers + Pydantic models for KBs, Documents, Chunks

**Key Tables**: `knowledge_bases`, `documents`, `processing_tasks`, `chunks`, `conversations`

**Deliverables**:
- CRUD APIs for knowledge bases
- Document upload with S3 storage
- Chunk CRUD with active/inactive toggle
- Pydantic validation for all request/response models

**RAGFlow Learning**: Adopt their entity model (KB → Document → Chunk hierarchy) but use Pydantic instead of raw dicts, SQLAlchemy instead of Peewee, explicit router registration instead of auto-discovery.

**Effort**: 1-2 weeks

---

#### 1.2 Document Parsing Pipeline

**What**: Celery-based async pipeline: upload → parse → chunk → embed → index

**Implementation**:
- Parser registry with extension-based routing
- Start with 4 parsers: PDF (PyMuPDF + layout detection), DOCX (python-docx), HTML (BeautifulSoup), Markdown
- Token-based chunking with configurable size, overlap, delimiters
- Batch embedding via litellm
- Qdrant upsert with dense + sparse vectors

**RAGFlow Learning**: Adopt their task splitting pattern (PDFs by page range) and content-hash deduplication (xxhash64). Skip the ONNX layout models initially — use `unstructured.io` or PyMuPDF's built-in layout detection.

**Effort**: 2-3 weeks

---

#### 1.3 Hybrid Retrieval with Citations

**What**: Query → embed → hybrid search (dense + sparse in Qdrant) → threshold filter → context assembly → LLM with citations

**Implementation**:
- Use Qdrant's native RRF fusion (better than RAGFlow's weighted sum)
- Token-aware context window construction (97% budget)
- Citation enforcement prompt template (adapted from RAGFlow's `citation_prompt.md`)
- Citation extraction post-processing
- Streaming response with FastAPI StreamingResponse

**RAGFlow Learning**: Adopt their citation prompt rules (must-cite/must-not-cite matrix). Adopt their `kb_prompt()` formatting pattern. Use configurable `vector_similarity_weight` per dialog/assistant.

**Effort**: 2 weeks

---

#### 1.4 Chunk Explorer UI

**What**: React page to view, search, edit, and toggle chunks

**Implementation**:
- Chunk list with search, filtering, pagination
- Chunk detail with inline editing + re-embedding
- Active/inactive toggle
- Retrieval test panel (query → see scored results)

**RAGFlow Learning**: Adopt their three-panel layout (document list → chunk list → chunk detail). The toggle feature is their best UX pattern — keep it.

**Effort**: 1-2 weeks

---

#### 1.5 Retrieval Test Endpoint

**What**: API to test retrieval without LLM generation, returning individual score components and timing

**RAGFlow Learning**: Direct copy of their `/chunk/retrieval_test` concept, enhanced with latency breakdown and score decomposition.

**Effort**: 3-5 days

---

### Phase 1 Total: ~7-9 weeks
### Phase 1 Outcome: Functional RAG system with document ingestion, hybrid search, citations, chunk management, and retrieval debugging.

---

## Phase 2: Core Architecture Upgrades (Medium Effort, High Impact)

### Milestone: "Production-ready RAG with quality controls"

#### 2.1 Model-Based Reranking

**What**: Add cross-encoder reranking as optional step after hybrid search

**Implementation**:
- Integrate Cohere Rerank v3.5 or Jina Reranker v2 via litellm
- Per-assistant configuration (rerank model, top-K before rerank)
- Reranking endpoint for A/B testing

**RAGFlow Learning**: Adopt their `rerank_by_model()` pattern. Their default of reranking top-1024 then taking top-N is correct.

**Effort**: 1 week

---

#### 2.2 Multi-Turn Conversation Support

**What**: Query refinement for follow-up questions, conversation history management

**Implementation**:
- LLM-based query refinement (last 3 messages → standalone query)
- Conversation persistence with message history
- Token-aware history truncation

**RAGFlow Learning**: Adopt their multi-turn refinement prompt. Their approach of combining last 3 turns is practical.

**Effort**: 1 week

---

#### 2.3 Auto Keyword & Question Generation

**What**: LLM-generated keywords and questions per chunk for improved recall

**Implementation**:
- Optional post-chunking step
- Batch LLM calls (10-20 chunks per call)
- Store keywords as Qdrant payload for sparse vector matching
- Configurable per KB (opt-in)

**RAGFlow Learning**: Their `auto_keywords` and `auto_questions` parameters stored in `important_kwd` and `question_kwd` fields are effective. The 30x BM25 weight boost for keywords is aggressively high but works.

**Effort**: 1 week

---

#### 2.4 Advanced Parser: Layout-Aware PDF Processing

**What**: Replace basic PDF parser with layout-aware processing

**Options** (pick one):
1. **unstructured.io** — Best general-purpose option, handles layout, tables, images
2. **Docling** (IBM) — Strong table extraction, open-source
3. **RAGFlow's ONNX models** — Best quality but hardest to integrate

**Implementation**:
- Swap PDF parser implementation behind the existing registry interface
- Add layout type annotations to ContentBlocks
- Table-aware chunking (tables as atomic units with context)

**RAGFlow Learning**: Their key insight is treating tables and figures as special blocks with surrounding context. This is worth adopting regardless of which parser you use.

**Effort**: 2 weeks

---

#### 2.5 Metadata & Tag System

**What**: Custom metadata fields per KB, tag management, metadata-based filtering in retrieval

**Implementation**:
- Metadata schema definition at KB level (Pydantic validated)
- Metadata extraction during parsing (LLM-based or rule-based)
- Qdrant payload indexes for metadata filtering
- Tag CRUD with bulk operations
- Metadata filter in retrieval queries

**RAGFlow Learning**: Adopt their concept of KB-level metadata schema. Improve by adding Pydantic validation and typed fields.

**Effort**: 1-2 weeks

---

#### 2.6 Observability & Tracing

**What**: Structured logging for every RAG operation, retrieval quality dashboard

**Implementation**:
- `RetrievalTrace` dataclass logged for every query
- PostgreSQL table for trace storage
- Analytics endpoint (avg latency, score distributions, zero-result queries)
- Integrate with OpenTelemetry for distributed tracing

**RAGFlow Learning**: RAGFlow's Langfuse integration is good inspiration. Their pipeline operation logs are useful for debugging parsing issues. But they lack retrieval-level tracing — this is a gap we fill.

**Effort**: 1-2 weeks

---

#### 2.7 Multi-Tenant Support

**What**: Organization-level isolation for KBs, documents, and LLM configuration

**Implementation**:
- Add `organization_id` to core tables
- FastAPI dependency for tenant context extraction
- Per-org LLM configuration table
- Token usage tracking per organization

**RAGFlow Learning**: Adopt their Tenant → UserTenant → TenantLLM schema pattern. Improve with row-level security in PostgreSQL.

**Effort**: 1-2 weeks

---

### Phase 2 Total: ~8-11 weeks
### Phase 2 Outcome: Production-hardened RAG with reranking, multi-turn, auto-keywords, advanced parsing, metadata, observability, and multi-tenancy.

---

## Phase 3: Advanced Features (High Effort, Strategic Impact)

### Milestone: "Best-in-class RAG platform"

#### 3.1 Knowledge Graph Augmentation (GraphRAG)

**What**: Entity/relation extraction from chunks, knowledge graph storage, graph-enhanced retrieval

**Implementation**:
- LLM-based entity extraction during ingestion
- Entity resolution (deduplication)
- Store in Neo4j or Qdrant with graph-like queries
- N-hop expansion during retrieval
- Community summaries for high-level Q&A

**RAGFlow Learning**: Adopt their lightweight extraction (single-pass, not Microsoft's multi-gleaning). Their N-hop expansion with distance-dampened scoring is clever. Their community detection via Leiden algorithm is overkill for most use cases.

**Effort**: 4-6 weeks

---

#### 3.2 Semantic Chunking

**What**: Embedding-based boundary detection for more coherent chunks

**Implementation**:
- Embed individual sentences
- Compute cosine distances between adjacent sentences
- Split at high-distance points (semantic boundaries)
- Fall back to token-budget merging for large segments

**RAGFlow Learning**: RAGFlow doesn't have this — it's our improvement. But combine with their token-budget approach as a safety net.

**Effort**: 1-2 weeks

---

#### 3.3 Hierarchical Chunking with Parent Expansion

**What**: Create large "parent" chunks and small "child" chunks. Retrieve by child, expand to parent for LLM context.

**Implementation**:
- Parent chunks: 3× normal size with 20% overlap
- Child chunks: normal size, linked to parent
- On retrieval: find matching children → deduplicate parents → use parents for context
- Store parent-child relationships in chunk metadata

**RAGFlow Learning**: RAGFlow has basic "children delimiters" but not true parent expansion. Our implementation goes further.

**Effort**: 2 weeks

---

#### 3.4 Evaluation Framework

**What**: Automated RAG quality evaluation with golden datasets

**Implementation**:
- Test dataset management (question + expected answer + relevant chunk IDs)
- Evaluation metrics: faithfulness, answer relevance, context relevance, MRR, NDCG
- Automated runs against different configs
- Comparison dashboard

**RAGFlow Learning**: RAGFlow has the API scaffolding for evaluation (`evaluation_app.py`) but metrics computation is largely TODO. We need to build this properly using frameworks like RAGAS.

**Effort**: 3-4 weeks

---

#### 3.5 Guardrails & Content Moderation

**What**: Input/output validation, topic restriction, PII detection

**Implementation**:
- Input guardrails: topic classification, injection detection
- Output guardrails: citation verification, factuality check, PII redaction
- Configurable per assistant/dialog

**RAGFlow Learning**: RAGFlow relies solely on prompt engineering for safety. We add programmatic guardrails.

**Effort**: 2-3 weeks

---

#### 3.6 Advanced Retrieval Features

**What**: Query decomposition, adaptive retrieval, caching

**Implementation**:
- Complex query decomposition into sub-queries
- Adaptive top-K based on query complexity
- Query embedding cache (Redis)
- Reciprocal Rank Fusion for multi-source retrieval

**Effort**: 3-4 weeks

---

### Phase 3 Total: ~15-21 weeks
### Phase 3 Outcome: Enterprise-grade RAG with knowledge graphs, semantic chunking, evaluation, guardrails, and advanced retrieval.

---

## Summary Timeline

```
                Phase 1          Phase 2           Phase 3
              (7-9 weeks)     (8-11 weeks)     (15-21 weeks)
              ┌──────────┐    ┌──────────────┐  ┌───────────────┐
Week 1-9      │Foundation│    │              │  │               │
              │ Schema   │    │              │  │               │
              │ Parsing  │    │              │  │               │
              │ Retrieval│    │              │  │               │
              │ Chunks UI│    │              │  │               │
              │ Citations│    │              │  │               │
              └──────────┘    │              │  │               │
Week 10-20                    │ Reranking    │  │               │
                              │ Multi-turn   │  │               │
                              │ Auto KW/Q    │  │               │
                              │ Adv. Parser  │  │               │
                              │ Metadata     │  │               │
                              │ Observability│  │               │
                              │ Multi-tenant │  │               │
                              └──────────────┘  │               │
Week 21-40                                      │ GraphRAG      │
                                                │ Semantic Chunk│
                                                │ Hierarchical  │
                                                │ Evaluation    │
                                                │ Guardrails    │
                                                │ Adv. Retrieval│
                                                └───────────────┘

Phase 1 = Functional RAG with quality controls
Phase 2 = Production-ready enterprise platform
Phase 3 = Best-in-class RAG with advanced features
```

---

## Technology Stack Decisions

| Component | Our Choice | Rationale |
|-----------|-----------|-----------|
| **API** | FastAPI | Native async, auto-docs, Pydantic, better than Flask/Quart |
| **ORM** | SQLAlchemy 2.0 + asyncpg | Async, mature ecosystem, migrations via Alembic |
| **DB** | PostgreSQL | JSONB for configs, row-level security, proven at scale |
| **Vector DB** | Qdrant | Native hybrid search (dense + sparse), payload filtering, quantization |
| **Task Queue** | Celery + Redis | Monitoring (Flower), dead letters, rate limiting, proven |
| **Object Storage** | MinIO (local) / S3 (prod) | Compatible APIs, seamless migration |
| **LLM** | litellm | 100+ providers, unified interface, no custom wrappers needed |
| **Embeddings** | OpenAI text-embedding-3-small (start) | Good quality, fast, cheap. Switch to BGE-M3 for multilingual |
| **Reranker** | Cohere Rerank v3.5 | Best price/performance, 4K context window |
| **Frontend** | React + Vite + Tailwind + Zustand | Modern, fast, good DX |
| **Containerization** | Docker Compose (dev) / K8s (prod) | Standard deployment |
| **Observability** | OpenTelemetry + Langfuse | Distributed tracing + LLM-specific metrics |

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| PDF parsing quality | Start with PyMuPDF, add unstructured.io as fallback. Don't block on perfect parsing. |
| LLM costs | Enable per-query cost tracking from day 1. Use caching. Use smaller models for extraction. |
| Retrieval quality | Ship retrieval test endpoint in Phase 1. Iterate based on real queries. |
| Scale concerns | Qdrant handles millions of vectors. PostgreSQL handles millions of rows. Scale issues are Phase 3 problems. |
| LLM hallucination | Citation enforcement + empty_response fallback from day 1. Add guardrails in Phase 3. |
| Embedding model lock-in | Store model name per KB. Document that model changes require re-indexing. |
