# Implementation Plan: Document-Centric Data Handling

## Priority Focus Feature — Deep Dive

This document provides a complete implementation guide for rebuilding RAGFlow's document-centric data handling in our stack (Python, FastAPI, Qdrant, React).

---

## 1. How RAGFlow Does It (Analysis)

### Document Ingestion Pipeline

**Entry Point**: `api/apps/document_app.py` → `POST /document/upload`

**Flow**:
1. **Upload**: Multipart file → validate extension/size → store binary in MinIO/S3
2. **Record**: Create `Document` row in MySQL (status=UNSTART, parser_config from KB)
3. **Task Split**: `task_service.queue_tasks()` splits into parallelizable units:
   - PDF: 12 pages per task
   - Excel: 3000 rows per task  
   - Others: 1 task per document
4. **Queue**: Publish tasks to Redis queue
5. **Worker**: Background worker picks up task → runs pipeline

### Chunking Strategy

**File**: `rag/flow/chunker/token_chunker.py`

**Algorithm (two-stage)**:

```
Stage 1: Delimiter-based splitting
  - Split by primary delimiters (newlines, custom delimiters)
  - Each split becomes a candidate segment

Stage 2: Token-budget merging
  - Iterate through segments
  - Accumulate text until chunk_token_size is reached (default 512)
  - On overflow: save accumulated text as chunk, start new accumulation
  - Apply overlap: include last N% tokens from previous chunk

Special handling:
  - Tables: wrap with surrounding text (configurable context window)
  - Images: wrap with surrounding text (configurable context window)
  - Children splitting: optional secondary split for fine-grained retrieval
```

**Configuration Parameters**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_token_num` | 512 | Target tokens per chunk |
| `delimiter` | `\n` | Primary split boundary |
| `overlapped_percent` | 0 | Overlap between adjacent chunks (0-100) |
| `table_context_size` | 0 | Tokens of surrounding text for tables |
| `image_context_size` | 0 | Tokens of surrounding text for images |
| `layout_recognize` | true | Use ONNX layout detection |
| `auto_keywords` | 0 | LLM-generated keywords per chunk |
| `auto_questions` | 0 | LLM-generated questions per chunk |

### How Chunks Are Stored

**Elasticsearch Schema** (from `conf/mapping.json`):
```json
{
  "doc_id": "keyword",
  "kb_id": "keyword", 
  "docnm_kwd": "keyword",
  "title_tks": "text (tokenized)",
  "content_ltks": "text (large-grained tokens)",
  "content_sm_ltks": "text (small-grained tokens)",
  "important_kwd": "keyword (auto-generated keywords)",
  "question_kwd": "keyword (auto-generated questions)",
  "question_tks": "text (tokenized questions)",
  "tag_kwd": "keyword (user tags)",
  "available_int": "integer (0=disabled, 1=active)",
  "positions": "text (PDF page coordinates as JSON)",
  "img_id": "keyword (associated image in MinIO)",
  "q_768_vec": "dense_vector (768-dim embedding)",
  "knowledge_graph_kwd": "keyword (entity/relation/graph/toc)",
  "create_timestamp_flt": "float (unix timestamp)",
  "chunk_order_flt": "float (order within document)"
}
```

### How Chunk Inspection Works

**API**: `api/apps/chunk_app.py`

- **List**: `POST /chunk/list` — Search chunks by keyword, paginated, with highlighting
- **Get**: `GET /chunk/get/{id}` — Full chunk data including embeddings metadata
- **Edit**: `POST /chunk/set` — Update text → auto-retokenize → re-embed → write to index
- **Toggle**: `POST /chunk/switch` — Set `available_int` to 0/1 (soft disable)
- **Create**: `POST /chunk/create` — Manual chunk creation with auto-embedding
- **Delete**: `DELETE /chunk/rm` — Hard delete + cleanup images

### UI/UX for Chunk Visibility

RAGFlow's frontend provides:
1. **Parsed Results View**: Shows layout-recognized document structure (page-by-page boxes)
2. **Chunk Results View**: Side-by-side comparison of parsed text vs final chunks
3. **Chunk Cards**: Each chunk as a card with content preview, active/inactive toggle, edit button
4. **Inline Editing**: Click chunk → edit text → save → auto re-embed
5. **Retrieval Testing**: Enter query → see which chunks get retrieved with scores

---

## 2. How to Rebuild This in Our System

### 2.1 Schema Design

#### PostgreSQL Tables

```sql
-- Knowledge Bases
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    embedding_model VARCHAR(100) NOT NULL DEFAULT 'openai/text-embedding-3-small',
    parser_config JSONB NOT NULL DEFAULT '{}',
    chunk_count INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id),
    name VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,
    content_hash VARCHAR(64),
    
    -- Parser config (overrides KB-level)
    parser_config_override JSONB,
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed, cancelled
    progress REAL DEFAULT 0.0,
    progress_message TEXT,
    error_message TEXT,
    
    -- Aggregated metrics
    chunk_count INTEGER DEFAULT 0,
    token_count BIGINT DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Processing Tasks
CREATE TABLE processing_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    task_type VARCHAR(50) NOT NULL,  -- parse, embed, extract_keywords
    
    -- Task splitting
    page_start INTEGER,
    page_end INTEGER,
    
    -- Deduplication
    config_digest VARCHAR(32),
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    progress REAL DEFAULT 0.0,
    error_message TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Chunk metadata (for fast SQL queries — actual chunks in Qdrant)
CREATE TABLE chunks (
    id UUID PRIMARY KEY,  -- Same as Qdrant point ID
    document_id UUID NOT NULL REFERENCES documents(id),
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id),
    
    -- Content
    content TEXT NOT NULL,
    content_tokens INTEGER NOT NULL,
    
    -- Ordering
    chunk_order INTEGER NOT NULL,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Source location (for PDF position tracking)
    source_pages INTEGER[],
    source_positions JSONB,  -- [{page, x, y, w, h}, ...]
    
    -- Associated media
    image_path VARCHAR(1000),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_kb ON chunks(kb_id);
CREATE INDEX idx_chunks_active ON chunks(kb_id, is_active);
```

#### Qdrant Collection Schema

```python
from qdrant_client import QdrantClient, models

def create_kb_collection(client: QdrantClient, kb_id: str, dim: int = 768):
    client.create_collection(
        collection_name=f"kb_{kb_id}",
        vectors_config={
            "dense": models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
    )
    
    # Create payload indexes for filtering
    for field in ["document_id", "kb_id", "is_active", "chunk_order"]:
        client.create_payload_index(
            collection_name=f"kb_{kb_id}",
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD 
                if field != "chunk_order" else models.PayloadSchemaType.FLOAT,
        )
```

#### Qdrant Point Payload

```python
{
    "document_id": "uuid",
    "kb_id": "uuid",
    "document_name": "Safety_Guidelines.pdf",
    "content": "Full chunk text...",
    "content_tokens": 342,
    "chunk_order": 5,
    "is_active": True,
    "metadata": {
        "department": "Engineering",
        "last_updated": "2024-03-15",
    },
    "auto_keywords": ["safety", "training", "PPE"],
    "auto_questions": ["What safety training is required?"],
    "source_pages": [3, 4],
    "image_path": "chunks/uuid/img_001.png",
    "created_at": "2024-03-01T12:00:00Z",
}
```

### 2.2 APIs Needed

```python
# FastAPI Router: /api/v1/documents

@router.post("/upload")
async def upload_document(
    kb_id: UUID,
    file: UploadFile,
    parser_config: Optional[ParserConfigOverride] = None,
) -> DocumentResponse:
    """Upload file → store in S3 → create document record → queue processing."""

@router.get("/{document_id}")
async def get_document(document_id: UUID) -> DocumentDetailResponse:
    """Get document with processing status and chunk count."""

@router.get("/{document_id}/status")
async def get_processing_status(document_id: UUID) -> ProcessingStatusResponse:
    """Real-time processing progress (for polling or SSE)."""

@router.post("/{document_id}/reparse")
async def reparse_document(
    document_id: UUID,
    parser_config: Optional[ParserConfigOverride] = None,
) -> TaskResponse:
    """Re-parse with new config (deletes old chunks, creates new tasks)."""

@router.delete("/{document_id}")
async def delete_document(document_id: UUID):
    """Delete document + all chunks from Qdrant + file from S3."""


# FastAPI Router: /api/v1/chunks

@router.get("/")
async def list_chunks(
    kb_id: UUID,
    document_id: Optional[UUID] = None,
    query: Optional[str] = None,  # Full-text search in chunk content
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedChunkResponse:
    """List/search chunks with filtering and pagination."""

@router.get("/{chunk_id}")
async def get_chunk(chunk_id: UUID) -> ChunkDetailResponse:
    """Get full chunk data including content, metadata, source position."""

@router.put("/{chunk_id}")
async def update_chunk(chunk_id: UUID, body: ChunkUpdateRequest) -> ChunkResponse:
    """Update chunk content → auto re-tokenize → re-embed → update Qdrant."""

@router.patch("/{chunk_id}/toggle")
async def toggle_chunk(chunk_id: UUID, is_active: bool) -> ChunkResponse:
    """Activate/deactivate chunk (updates Qdrant payload filter)."""

@router.post("/")
async def create_chunk(body: ChunkCreateRequest) -> ChunkResponse:
    """Manually create a chunk → embed → store in Qdrant."""

@router.delete("/{chunk_id}")
async def delete_chunk(chunk_id: UUID):
    """Hard delete chunk from Qdrant + PostgreSQL + associated images from S3."""

@router.post("/retrieval-test")
async def test_retrieval(body: RetrievalTestRequest) -> RetrievalTestResponse:
    """Test retrieval: query → search → return ranked chunks with scores."""
```

### 2.3 Backend Logic

#### Document Processing Pipeline (Celery)

```python
# tasks/ingestion.py
from celery import chain, group

@celery_app.task(bind=True, max_retries=3)
def parse_document(self, document_id: str, task_id: str):
    """Parse document into structured content blocks."""
    document = DocumentService.get(document_id)
    file_bytes = storage.get(document.storage_path)
    
    parser = ParserRegistry.get(document.file_type)
    config = document.effective_parser_config  # KB + override merged
    
    blocks = parser.parse(file_bytes, config)
    
    # Store intermediate result for chunking
    cache.set(f"parsed:{task_id}", blocks, ttl=3600)
    update_progress(document_id, 0.3, "Parsing complete")

@celery_app.task(bind=True, max_retries=3)
def chunk_document(self, document_id: str, task_id: str):
    """Split parsed blocks into semantic chunks."""
    blocks = cache.get(f"parsed:{task_id}")
    config = DocumentService.get(document_id).effective_parser_config
    
    chunker = TokenChunker(
        chunk_token_size=config.get("chunk_token_num", 512),
        delimiter=config.get("delimiter", "\n"),
        overlap_percent=config.get("overlap_percent", 0),
    )
    
    chunks = chunker.chunk(blocks)
    cache.set(f"chunks:{task_id}", chunks, ttl=3600)
    update_progress(document_id, 0.5, f"Created {len(chunks)} chunks")

@celery_app.task(bind=True, max_retries=3)
def embed_and_store(self, document_id: str, task_id: str):
    """Generate embeddings and store in Qdrant."""
    chunks = cache.get(f"chunks:{task_id}")
    document = DocumentService.get(document_id)
    kb = KnowledgeBaseService.get(document.kb_id)
    
    embedder = EmbeddingService(model=kb.embedding_model)
    
    # Batch embed
    texts = [c.text for c in chunks]
    vectors = embedder.embed_batch(texts, batch_size=32)
    
    # Prepare Qdrant points
    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid4())
        points.append(models.PointStruct(
            id=point_id,
            vector={"dense": vector},
            payload={
                "document_id": str(document_id),
                "kb_id": str(document.kb_id),
                "document_name": document.name,
                "content": chunk.text,
                "content_tokens": chunk.token_count,
                "chunk_order": i,
                "is_active": True,
                "metadata": chunk.metadata,
                "source_pages": chunk.source_pages,
            },
        ))
        
        # Also save to PostgreSQL for fast SQL queries
        ChunkService.create(
            id=point_id,
            document_id=document_id,
            kb_id=document.kb_id,
            content=chunk.text,
            content_tokens=chunk.token_count,
            chunk_order=i,
        )
    
    # Bulk upsert to Qdrant
    qdrant.upsert(collection_name=f"kb_{document.kb_id}", points=points)
    
    update_progress(document_id, 1.0, "Complete")
    DocumentService.update(document_id, status="completed", chunk_count=len(chunks))


def process_document(document_id: str):
    """Orchestrate the full processing pipeline."""
    task_id = str(uuid4())
    chain(
        parse_document.s(document_id, task_id),
        chunk_document.s(document_id, task_id),
        embed_and_store.s(document_id, task_id),
    ).apply_async()
```

#### Chunk Update with Re-embedding

```python
# services/chunk_service.py
async def update_chunk(chunk_id: UUID, new_content: str):
    """Update chunk content and re-embed."""
    chunk = await ChunkRepository.get(chunk_id)
    kb = await KBRepository.get(chunk.kb_id)
    
    # Re-embed
    embedder = EmbeddingService(model=kb.embedding_model)
    new_vector = await embedder.embed(new_content)
    new_token_count = count_tokens(new_content)
    
    # Update Qdrant
    qdrant.set_payload(
        collection_name=f"kb_{chunk.kb_id}",
        payload={"content": new_content, "content_tokens": new_token_count},
        points=[str(chunk_id)],
    )
    qdrant.update_vectors(
        collection_name=f"kb_{chunk.kb_id}",
        points=[models.PointVectors(id=str(chunk_id), vector={"dense": new_vector})],
    )
    
    # Update PostgreSQL
    await ChunkRepository.update(chunk_id, content=new_content, content_tokens=new_token_count)
```

### 2.4 UI Ideas

#### Chunk Explorer Page

```
┌─────────────────────────────────────────────────────────┐
│  Knowledge Base > Technical Docs > Safety Guidelines.pdf │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ 🔍 Search chunks...    [Active ▾] [Sort: Order ▾]  ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  Showing 47 chunks (3 inactive)                         │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ #1 │ ● Active    │ 342 tokens │ Pages 1-2          ││
│  │ ──────────────────────────────────────────────────  ││
│  │ All personnel must complete safety training within  ││
│  │ 30 days of hire. The training includes fire         ││
│  │ evacuation procedures, chemical handling, and PPE...││
│  │                                                     ││
│  │ [Edit] [Toggle Off] [Delete] [View Source PDF]      ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │ #2 │ ○ Inactive  │ 287 tokens │ Page 3             ││
│  │ ──────────────────────────────────────────────────  ││
│  │ Table of Contents... (disabled by admin)            ││
│  │ [Edit] [Toggle On] [Delete]                         ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  [< Prev] Page 1 of 5 [Next >]                         │
└─────────────────────────────────────────────────────────┘
```

#### Chunk Edit Modal

```
┌─────────────────────────────────────────────────────────┐
│  Edit Chunk #1                                    [X]   │
│                                                         │
│  Content:                                               │
│  ┌─────────────────────────────────────────────────────┐│
│  │ All personnel must complete safety training within  ││
│  │ 30 days of hire. The training includes fire         ││
│  │ evacuation procedures, chemical handling, and       ││
│  │ personal protective equipment (PPE) requirements.   ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  Tokens: 342 → 342                                      │
│  ⚠️ Saving will re-generate the embedding vector        │
│                                                         │
│  Metadata:                                              │
│  Department: [Engineering    ]                          │
│  Tags: [safety] [training] [+]                          │
│                                                         │
│  [Cancel]                              [Save & Re-embed]│
└─────────────────────────────────────────────────────────┘
```

#### Retrieval Test Panel

```
┌─────────────────────────────────────────────────────────┐
│  🔬 Retrieval Test                                      │
│                                                         │
│  Query: [What safety training is required?          ]   │
│  KBs: [✓ Technical Docs] [✓ HR Policies]               │
│  [Test Retrieval]                                       │
│                                                         │
│  Results (8 chunks, 12ms):                              │
│                                                         │
│  #1 │ Score: 0.94 │ Safety_Guidelines.pdf, Chunk 1     │
│  "All personnel must complete safety training..."       │
│  Vector: 0.95 │ BM25: 0.82 │ Combined: 0.94            │
│                                                         │
│  #2 │ Score: 0.87 │ HR_Onboarding.docx, Chunk 12       │
│  "New employee orientation includes safety modules..."  │
│  Vector: 0.88 │ BM25: 0.79 │ Combined: 0.87            │
│                                                         │
│  #3 │ Score: 0.71 │ Safety_Guidelines.pdf, Chunk 8     │
│  "Annual safety refresher courses are mandatory..."     │
│  Vector: 0.72 │ BM25: 0.65 │ Combined: 0.71            │
└─────────────────────────────────────────────────────────┘
```

### 2.5 Improvements Over RAGFlow

1. **Qdrant-native sparse vectors**: RAGFlow uses Elasticsearch for BM25 + vectors in same index. We use Qdrant's native sparse vector support — simpler architecture, one less service.

2. **Async-first**: All DB operations async (SQLAlchemy + asyncpg). No event loop blocking.

3. **Celery for task processing**: Built-in monitoring (Flower), dead letters, rate limiting. RAGFlow's custom Redis queue lacks these.

4. **Pydantic validation**: All parser configs validated by Pydantic models. RAGFlow uses raw dicts.

5. **WebSocket/SSE progress**: Real-time progress via SSE instead of polling. RAGFlow uses background thread polling.

6. **Chunk versioning**: Track content changes over time (RAGFlow overwrites). Enables audit trail.

7. **Batch operations**: Bulk toggle, bulk delete, bulk re-embed. RAGFlow processes one chunk at a time.
