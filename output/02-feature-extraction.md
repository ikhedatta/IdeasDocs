# 2. Feature Extraction — Core Deliverable

This document analyzes 12 key features from RAGFlow with adopt/skip recommendations and implementation guidance.

---

## Feature 1: Deep Document Parsing (ONNX Layout Recognition)

### What Problem It Solves
Naive text extraction (PyPDF2, pdfminer) produces flat text streams that lose document structure — headers become body text, tables become gibberish, multi-column layouts interleave incorrectly. This destroys retrieval quality.

### How It Is Implemented

**Key Files**:
- `deepdoc/parser/pdf_parser.py` — Main PDF parser with layout-aware extraction
- `deepdoc/vision/layout_recognizer.py` — ONNX neural network for detecting text/table/figure/header regions
- `deepdoc/vision/table_structure_recognizer.py` — Table cell structure detection
- `deepdoc/vision/ocr.py` — Character recognition for scanned documents
- `deepdoc/parser/pdf_parser.py:173-204` — XGBoost feature extraction (30+ features)

**Data Structures**:
- Bounding boxes with layout type annotations (`text`, `table`, `figure`, `header`, `footer`)
- XGBoost feature vectors for merge decisions (spatial + linguistic + semantic features)

**Flow**:
1. Render PDF pages as images
2. Run ONNX LayoutRecognizer → detect regions (text, table, figure, header)
3. Run OCR on detected text regions
4. Run TableStructureRecognizer on table regions → extract structured tables
5. XGBoost model classifies whether adjacent text blocks should merge (30+ spatial/linguistic features)
6. Output: ordered list of content blocks with type, position, and text

### Why It Is Valuable
- **Retrieval quality**: Chunks respect document structure → better semantic coherence
- **Table handling**: Tables preserved as structured data, not garbled text
- **Multi-column support**: Correct reading order preserved
- **Scanned document support**: OCR pipeline handles non-digital PDFs

### Should We Adopt It?
**Yes, with modification.** The ONNX models are the key innovation. But:
- Consider using `unstructured.io` or `docling` as alternatives (RAGFlow supports both as options)
- The XGBoost merge model is trained on RAGFlow's dataset — may need retraining for your domain
- Start with a simpler layout parser and upgrade as needed

### Implementation Plan
→ See [implementation/document-centric-data-handling.md](implementation/document-centric-data-handling.md)

---

## Feature 2: Hybrid Search with Configurable Fusion Weights

### What Problem It Solves
Pure vector search misses exact keyword matches (product codes, legal terms, proper nouns). Pure BM25 search misses semantic meaning. Hybrid search combines both but the optimal ratio depends on the use case.

### How It Is Implemented

**Key Files**:
- `rag/nlp/search.py` — `Dealer` class: core search orchestration
- `rag/nlp/query.py` — `FulltextQueryer`: BM25 query construction with synonyms
- `common/doc_store/doc_store_base.py` — `FusionExpr`, `MatchTextExpr`, `MatchDenseExpr`
- `common/doc_store/es_conn.py` — Elasticsearch DSL construction for hybrid queries

**Data Structures**:
```python
FusionExpr(
    MatchTextExpr(fields=["content_ltks", "title_tks", "important_kwd"], 
                  query=tokenized_query, minimum_should_match="60%"),
    MatchDenseExpr(vector_field="q_768_vec", query_vector=embedding, 
                   similarity=0.1, topn=top_k),
    method="weighted_sum",
    weights=[0.05, 0.95]  # keyword, vector
)
```

**Scoring Formula**:
```
final_score = vector_similarity_weight × cosine_sim + (1 - vector_similarity_weight) × BM25_score
```

Then optionally:
```
reranked_score = token_weight × token_similarity + vector_weight × vector_similarity + pagerank + tag_features
```

**Pagination Strategy**: Fetch `top_k` results (up to 1024), rerank all, then paginate by `top_n`

### Why It Is Valuable
- **Per-dialog tuning**: Each chat application can have different fusion weights
- **Graceful fallback**: If vector search returns nothing, retries with looser text matching (10% min match)
- **Real-world tested**: Default 95% vector / 5% keyword works well for general knowledge; can shift for technical/legal domains

### Should We Adopt It?
**Yes.** This is a must-have for any production RAG system.

### Implementation Plan
1. Qdrant supports hybrid search via sparse+dense vectors — use this natively
2. Store `vector_similarity_weight` per dialog/assistant configuration
3. Implement BM25 via Qdrant's sparse vectors (or a separate Elasticsearch index)
4. Build a `/retrieval/test` endpoint that shows individual keyword and vector scores

---

## Feature 3: Chunk-Level CRUD with Toggle and Re-embedding

### What Problem It Solves
After automated chunking, some chunks are garbage (boilerplate, headers, footers, malformed text). Without chunk-level management, you must re-parse the entire document. Also, domain experts may want to manually refine chunks.

### How It Is Implemented

**Key Files**:
- `api/apps/chunk_app.py` — REST endpoints: list, get, set, create, delete, switch
- `common/doc_store/es_conn.py` — Direct chunk manipulation in Elasticsearch

**Endpoints**:
- `POST /chunk/list` — Search chunks by keyword with pagination (highlights matches)
- `GET /chunk/get/{chunk_id}` — Retrieve single chunk with full metadata
- `POST /chunk/set` — Update content → auto-retokenize → re-embed → update index
- `POST /chunk/switch` — Toggle `available_int` flag (soft disable without deletion)
- `POST /chunk/create` — Manually create new chunk with auto-embedding
- `DELETE /chunk/rm` — Hard delete chunk + cleanup associated images

**Toggle mechanism**: `available_int` field (0/1) — disabled chunks stay indexed but excluded from search via filter

### Why It Is Valuable
- **Human-in-the-loop QA**: Domain experts can review, edit, and approve chunks before they go live
- **Non-destructive**: Toggle off bad chunks instantly without re-processing
- **Iterative improvement**: Edit chunk text → auto re-embed → immediately live
- **Debugging**: Inspect exactly what the system retrieves

### Should We Adopt It?
**Yes.** This is essential for a controlled RAG system where approved content is the knowledge source.

### Implementation Plan
→ See [implementation/visual-knowledge-base-management.md](implementation/visual-knowledge-base-management.md)

---

## Feature 4: Citation Enforcement via Prompt Engineering

### What Problem It Solves
LLMs hallucinate. In a controlled RAG system, every factual claim must be traceable to source chunks. Without explicit citation rules, the model will paraphrase and synthesize without attribution.

### How It Is Implemented

**Key Files**:
- `rag/prompts/citation_prompt.md` — Detailed citation rules
- `rag/prompts/generator.py` — `kb_prompt()` formats chunks with `ID: X` markers
- `agent/component/llm.py` — Conditional citation injection

**Citation Rules** (from `citation_prompt.md`):
- Format: `[ID:i]` placed BEFORE punctuation
- Max 4 citations per sentence
- **Must cite**: quantitative data, temporal claims, causal relationships, technical definitions, comparative statements
- **Must NOT cite**: common knowledge, transitional phrases, general introductions
- Fallback: "If the information isn't in the provided context, say so"

**Context Formatting** (from `kb_prompt()`):
```
ID: 1
├── Title: Technical_Specification_v2.pdf
├── URL: https://...
├── Department: Engineering
└── Content:
The maximum operating temperature is 85°C...
```

**Citation Post-processing**:
- Auto-citation repair for malformed references
- Vector similarity-based auto-citation when model doesn't cite
- Reference aggregation for response metadata

### Why It Is Valuable
- **Traceability**: Every claim is linked to source documents
- **Audit-ready**: Compliance teams can verify AI responses
- **User trust**: Citations increase user confidence in answers
- **Hallucination detection**: Claims without citations are flagged

### Should We Adopt It?
**Yes, immediately.** This is the #1 requirement for a controlled RAG system.

### Implementation Plan
1. Create a Jinja2 prompt template with citation rules adapted to your format
2. Format retrieved chunks with unique IDs in the context
3. Post-process LLM output to extract `[ID:X]` references → map to source documents
4. Return references alongside the answer in the API response
5. Frontend: render citations as clickable links to source chunks

---

## Feature 5: Multi-format Document Parser Registry

### What Problem It Solves
Enterprises store knowledge in PDFs, Word docs, Excel sheets, PowerPoints, HTML, emails, images, and more. A RAG system that only handles PDFs misses most enterprise content.

### How It Is Implemented

**Key Files**:
- `deepdoc/parser/` — 16 specialized parsers
- `rag/flow/parser/parser.py` — Parser component with format routing

**Supported Formats**:

| Format | Parser | Approach |
|--------|--------|----------|
| PDF | `pdf_parser.py` | ONNX layout + OCR + XGBoost merge |
| DOCX | `docx_parser.py` | python-docx structured extraction |
| XLSX/CSV | `excel_parser.py` | Row-based parsing with header detection |
| PPTX | `pptx_parser.py` | Slide-by-slide text + image extraction |
| HTML | `html_parser.py` | BeautifulSoup with boilerplate removal |
| Markdown | `markdown_parser.py` | Section-based splitting |
| Images | OCR + Vision LLM | Layout recognition → text extraction |
| Audio/Video | ASR model | Transcription → text |
| Email (.eml) | Email parser | Header + body + attachment extraction |
| Code files | Code parser | Language-aware section splitting |

**Routing Logic** (in `parser.py`): Switch statement on `doc.suffix` selects appropriate parser.

### Why It Is Valuable
- **Enterprise coverage**: Handles the long tail of document formats
- **Unified pipeline**: All formats produce the same structured output (boxes/markdown)
- **Extensible**: Adding a new format = adding one parser class

### Should We Adopt It?
**Yes, incrementally.** Start with PDF + DOCX + XLSX, add formats as needed.

### Implementation Plan
1. Define a `BaseParser` protocol: `parse(file_bytes, config) → List[ContentBlock]`
2. Register parsers by file extension
3. Start with: `unstructured.io` for PDF/DOCX, `openpyxl` for Excel, `BeautifulSoup` for HTML
4. Add format-specific parsers as your users need them

---

## Feature 6: Task-Based Async Document Processing with Deduplication

### What Problem It Solves
Parsing large documents is slow (minutes for big PDFs). Synchronous processing times out. Re-parsing the same document with the same config wastes resources.

### How It Is Implemented

**Key Files**:
- `api/db/services/task_service.py` — `queue_tasks()`, task splitting, deduplication

**Task Splitting Logic**:
- PDFs: 12 pages per task (configurable)
- Excel: 3000 rows per task
- Others: 1 task per document

**Deduplication**: `xxhash64(chunking_config)` produces a digest. If a task with the same digest exists and completed successfully, chunks from the previous run are reused.

**State Machine**:
```
UNSTART → QUEUED → RUNNING → DONE | FAIL (max 3 retries)
```

**Progress Tracking**: Atomic updates via `DocumentService.update_progress()` running in background thread.

### Why It Is Valuable
- **Scalability**: Horizontal scaling of workers
- **Efficiency**: No redundant processing on re-parse with same config
- **Reliability**: Retry logic handles transient failures
- **UX**: Real-time progress bar in UI

### Should We Adopt It?
**Yes.** Use Celery or Dramatiq instead of custom Redis queue for better monitoring and reliability.

### Implementation Plan
1. Define Celery tasks: `parse_document`, `embed_chunks`, `build_graph`
2. Use task signatures for chaining: `parse | chunk | embed`
3. Implement content-hash deduplication at the task level
4. Expose WebSocket/SSE endpoint for real-time progress

---

## Feature 7: Knowledge Graph Augmentation (GraphRAG)

### What Problem It Solves
Standard chunk retrieval misses relationships between entities. "Who is the CEO of Company X?" requires connecting person → role → company across multiple chunks.

### How It Is Implemented

**Key Files**:
- `rag/graphrag/` — Knowledge graph construction and search
- `rag/graphrag/search.py` — `KGSearch.retrieval()` with N-hop expansion
- Entity/relation extraction via LLM prompts
- Community detection via Leiden algorithm

**Storage**: Entities, relations, and community reports stored as special chunk types in Elasticsearch with `knowledge_graph_kwd` field.

**Retrieval**: Query → entity/keyword matching → N-hop neighbor expansion → distance-dampened scoring → token-aware truncation.

### Why It Is Valuable
- **Multi-hop reasoning**: Connects dots across documents
- **Entity disambiguation**: Deduplicates entities via LLM resolution
- **Context enrichment**: Adds relational context to chunk-based retrieval

### Should We Adopt It?
**With modification, Phase 3.** GraphRAG is powerful but complex. Start with chunk-based retrieval, add graph augmentation for specific use cases (organizational data, product catalogs, compliance regulations).

### Implementation Plan
→ Covered in roadmap Phase 3

---

## Feature 8: Multi-Provider LLM Abstraction

### What Problem It Solves
Vendor lock-in on a single LLM provider. Need to switch between OpenAI, Anthropic, local models without code changes.

### How It Is Implemented

**Key Files**:
- `rag/llm/__init__.py` — Dynamic factory registration via `_FACTORY_NAME`
- `rag/llm/chat_model.py` — `Base` (OpenAI SDK) + `LiteLLMBase` (multi-provider)
- `rag/llm/embedding_model.py` — Embedding abstraction
- `rag/llm/rerank_model.py` — Reranking abstraction

**Registration Pattern**:
```python
class AnthropicChat(LiteLLMBase):
    _FACTORY_NAME = "Anthropic"
    # ...automatically registered at import time
```

**Usage**:
```python
model = ChatModel[factory_name](api_key, model_name, api_base)
response = await model.async_chat(system_prompt, history, gen_conf)
```

### Why It Is Valuable
- **Flexibility**: Switch LLM per tenant, per dialog, per task
- **Cost optimization**: Use cheap models for extraction, expensive for generation
- **Resilience**: Fall back to alternative provider on failure

### Should We Adopt It?
**Yes, simplified.** Use `litellm` directly (RAGFlow already does for most providers). Don't replicate 35 provider classes — `litellm` handles the mapping.

### Implementation Plan
1. `pip install litellm`
2. Configure models in settings: `{"chat": "openai/gpt-4o", "embed": "openai/text-embedding-3-small", "rerank": "cohere/rerank-v3.5"}`
3. Wrap `litellm.acompletion()` in a thin service class with retry/circuit-breaker

---

## Feature 9: Retrieval Testing Endpoint

### What Problem It Solves
When retrieval quality is poor, operators need to debug: Is the query being embedded correctly? Are the right chunks being retrieved? What are the scores?

### How It Is Implemented

**Key Files**:
- `api/apps/chunk_app.py` — `POST /chunk/retrieval_test`
- `rag/nlp/search.py` — `Dealer.search()` returns scored results

**Endpoint**: Accepts query text + KB IDs, returns ranked chunks with scores, highlights, and metadata. No LLM involved — pure retrieval testing.

### Why It Is Valuable
- **Debugging**: Isolate retrieval issues from generation issues
- **Tuning**: Adjust weights, thresholds, rerankers with immediate feedback
- **Confidence**: Verify the right content is being found before deploying

### Should We Adopt It?
**Yes, immediately.** This is a quick win with massive debugging value.

### Implementation Plan
→ See [implementation/retrieval-debugging-transparency.md](implementation/retrieval-debugging-transparency.md)

---

## Feature 10: Parser Configuration Per Document Type

### What Problem It Solves
Different document types need different parsing strategies. A legal contract needs different chunking than a product manual or a financial report.

### How It Is Implemented

**Key Files**:
- `api/apps/kb_app.py` — Parser config at KB level
- `api/apps/document_app.py` — Parser config override at document level
- `common/parser_config_utils.py` — Config merging logic

**Config Schema** (per KB or document):
```python
{
    "chunk_token_num": 512,        # Target chunk size in tokens
    "layout_recognize": True,       # Use ONNX layout detection
    "delimiter": "\n",             # Primary split delimiter
    "html4excel": False,           # Render Excel as HTML
    "raptor": {"use_raptor": False, "prompt": "..."},  # RAPTOR hierarchical
    "graphrag": {"use_graphrag": False},
    "entity_types": ["person", "org", "location"],
    "page_ranges": [[1, 10]],     # Parse specific pages only
    "auto_keywords": 0,           # Auto-extract N keywords per chunk
    "auto_questions": 0,          # Auto-generate N questions per chunk
}
```

### Why It Is Valuable
- **Flexibility**: One system handles diverse document types
- **Quality**: Optimal settings per content type
- **Control**: Override at document level for edge cases

### Should We Adopt It?
**Yes.** Config-driven parsing is essential for an enterprise platform.

### Implementation Plan
1. Define a `ParserConfig` Pydantic model with validation
2. Store config at knowledge base level with document-level overrides
3. Expose config UI with presets for common document types (legal, technical, financial)

---

## Feature 11: Automated Keyword and Question Generation

### What Problem It Solves
BM25 keyword search depends on exact term matches. If the chunk text uses one term and the user query uses a synonym, keyword search fails. Auto-generated keywords and questions improve recall.

### How It Is Implemented

**Key Files**:
- `rag/flow/extractor/` — LLM-based extraction components
- Parser config: `auto_keywords` and `auto_questions` parameters

**Approach**:
- Use LLM to generate N important keywords per chunk → stored in `important_kwd` field (weighted 30× in BM25)
- Use LLM to generate N questions each chunk can answer → stored in `question_kwd`/`question_tks` field
- Keywords and generated questions are indexed for BM25 matching

### Why It Is Valuable
- **Improved recall**: Bridges vocabulary gap between queries and documents
- **Question matching**: "What is the max temperature?" matches a chunk about operating specs even if the chunk text doesn't contain "max temperature"
- **Domain adaptation**: LLM generates domain-relevant synonyms

### Should We Adopt It?
**Yes, Phase 2.** Start without it (add later as retrieval quality optimization). LLM cost per chunk is a consideration.

### Implementation Plan
1. Add optional post-processing step after chunking
2. Batch chunks (10-20 per LLM call) for keyword/question generation
3. Store in separate Qdrant payload fields for BM25-style sparse vector matching
4. Make it configurable per KB (opt-in, with LLM cost warning)

---

## Feature 12: Multi-Tenant Architecture with Per-Tenant LLM Configuration

### What Problem It Solves
Enterprise deployments need isolation between teams/departments, each potentially using different LLM providers, API keys, and model configurations.

### How It Is Implemented

**Key Files**:
- `api/db/db_models.py` — `Tenant`, `UserTenant`, `TenantLLM` models
- `api/apps/tenant_app.py` — Tenant management
- `api/apps/llm_app.py` — Per-tenant LLM configuration

**Schema**:
```
Tenant: id, name, llm_id, embd_id, asr_id, parser_ids, credit
TenantLLM: tenant_id, llm_factory, llm_name, api_key, api_base, max_tokens, used_tokens
UserTenant: user_id, tenant_id, role (owner/admin/member), invited_by
```

**Isolation**: Every query filters by `tenant_id`. API tokens scoped to specific dialogs within a tenant.

### Why It Is Valuable
- **Department-level isolation**: Legal team uses different KBs and models than engineering
- **Cost tracking**: `used_tokens` per tenant for chargeback
- **Security**: Data never leaks between tenants

### Should We Adopt It?
**Yes, Phase 2.** Start single-tenant, add multi-tenancy when you need organizational isolation.

### Implementation Plan
1. Add `organization_id` to your core tables
2. Use FastAPI dependency injection for tenant context
3. Add per-org LLM configuration table
4. Implement token usage tracking for cost attribution
