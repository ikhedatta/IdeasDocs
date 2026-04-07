# Implementation Plan: Visual Knowledge Base Management

## Priority Focus Feature — Deep Dive

---

## 1. How RAGFlow Does It

### Knowledge Base Lifecycle

**Create KB** → `POST /kb/save`
- Name, description, embedding model, parser config
- Creates ES index with vector mapping specific to embedding dimension

**Upload Documents** → `POST /document/upload`
- Multipart file upload to KB
- Creates Document record, queues parsing task

**Parse Documents** → Background worker
- Runs through pipeline: parse → chunk → embed → index
- Real-time progress tracking

**Manage Chunks** → `chunk_app.py` endpoints
- List, search, edit, toggle, create, delete chunks
- Each operation updates both ES index and DB aggregates

**Search & Chat** → `dialog_app.py`
- Create Dialog (chat app) linked to KBs
- Query → retrieve from linked KBs → generate with citations

### KB-Level Configuration

From `api/apps/kb_app.py`:
```python
# Parser config stored at KB level
parser_config = {
    "chunk_token_num": 512,
    "layout_recognize": True,
    "delimiter": "\n",
    "html4excel": False,
    "raptor": {"use_raptor": False},
    "graphrag": {"use_graphrag": False},
    "auto_keywords": 0,
    "auto_questions": 0,
    "entity_types": ["person", "organization", "location"],
    "page_ranges": [],
    "tag_kb_ids": [],
}
```

### Metadata System

RAGFlow supports **custom metadata fields** at KB level:
- Define metadata schema on KB (e.g., `{"department": "string", "classification": "enum"}`)
- During parsing, extract or assign metadata values per chunk
- Metadata is indexed in Elasticsearch for filtering during retrieval
- Users can filter search results by metadata

### Tag Management

- **Tags** (`tag_kwd`): User-applied labels on chunks
- **Bulk operations**: Rename tag across all chunks, delete tag
- **Tag-based retrieval boost**: Tags can contribute to scoring during search

### KB Statistics

The KB record aggregates:
- `doc_num`: Total documents
- `chunk_num`: Total chunks across all documents
- `token_num`: Total tokens indexed
- Parsed/unparsed document status counts

---

## 2. Implementation Plan for Our System

### 2.1 Schema Design

```sql
-- Knowledge Bases (extended from previous document)
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Embedding config (immutable after first document indexed)
    embedding_model VARCHAR(100) NOT NULL DEFAULT 'openai/text-embedding-3-small',
    embedding_dimension INTEGER NOT NULL DEFAULT 1536,
    
    -- Default parser config for documents in this KB
    parser_config JSONB NOT NULL DEFAULT '{
        "chunk_token_size": 512,
        "chunk_overlap_percent": 10,
        "delimiter": "\\n",
        "use_layout_detection": true,
        "auto_keywords": 0,
        "auto_questions": 0
    }',
    
    -- Custom metadata schema
    metadata_schema JSONB DEFAULT '{}',
    -- Example: {"department": {"type": "string", "required": true},
    --           "classification": {"type": "enum", "values": ["public", "internal", "confidential"]}}
    
    -- Aggregated stats
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    active_chunk_count INTEGER DEFAULT 0,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',  -- active, archived, deleted
    
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(organization_id, name)
);

-- Tags (normalized)
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id),
    name VARCHAR(100) NOT NULL,
    color VARCHAR(7) DEFAULT '#6366f1',  -- Hex color for UI
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(kb_id, name)
);

-- Chunk-Tag many-to-many
CREATE TABLE chunk_tags (
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (chunk_id, tag_id)
);
```

### 2.2 API Design

```python
# ============================================
# Knowledge Base Management
# ============================================

@router.post("/knowledge-bases")
async def create_kb(body: KBCreateRequest) -> KBResponse:
    """Create knowledge base with parser config and metadata schema."""

@router.get("/knowledge-bases")
async def list_kbs(
    status: Optional[str] = "active",
    page: int = 1, 
    page_size: int = 20,
) -> PaginatedKBResponse:
    """List KBs with document/chunk stats."""

@router.get("/knowledge-bases/{kb_id}")
async def get_kb(kb_id: UUID) -> KBDetailResponse:
    """Get KB details including stats, config, metadata schema."""

@router.put("/knowledge-bases/{kb_id}")
async def update_kb(kb_id: UUID, body: KBUpdateRequest) -> KBResponse:
    """Update name, description, parser config. 
    Warning: changing parser config doesn't re-parse existing docs."""

@router.delete("/knowledge-bases/{kb_id}")
async def delete_kb(kb_id: UUID):
    """Soft-delete KB (archive). Hard delete requires separate endpoint."""

@router.get("/knowledge-bases/{kb_id}/stats")
async def get_kb_stats(kb_id: UUID) -> KBStatsResponse:
    """Detailed stats: doc count by status, chunk count by active/inactive, 
    token distribution, format breakdown."""

# ============================================
# Metadata Schema Management
# ============================================

@router.put("/knowledge-bases/{kb_id}/metadata-schema")
async def update_metadata_schema(
    kb_id: UUID, 
    body: MetadataSchemaRequest,
) -> MetadataSchemaResponse:
    """Define/update custom metadata fields for this KB.
    New fields are appended, existing fields can be updated (not deleted if chunks exist)."""

# ============================================
# Tag Management
# ============================================

@router.get("/knowledge-bases/{kb_id}/tags")
async def list_tags(kb_id: UUID) -> list[TagResponse]:
    """List all tags with chunk counts."""

@router.post("/knowledge-bases/{kb_id}/tags")
async def create_tag(kb_id: UUID, body: TagCreateRequest) -> TagResponse:
    """Create a new tag."""

@router.put("/tags/{tag_id}")
async def rename_tag(tag_id: UUID, body: TagRenameRequest) -> TagResponse:
    """Rename tag (updates all chunk associations)."""

@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: UUID):
    """Delete tag and remove from all chunks."""

@router.post("/chunks/bulk-tag")
async def bulk_tag_chunks(body: BulkTagRequest):
    """Add/remove tags from multiple chunks at once."""

# ============================================
# Document Management within KB
# ============================================

@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(
    kb_id: UUID,
    status: Optional[str] = None,
    file_type: Optional[str] = None,
    query: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedDocResponse:
    """List documents with filtering by status, type, name search."""

@router.post("/knowledge-bases/{kb_id}/documents/bulk-reparse")
async def bulk_reparse(
    kb_id: UUID,
    body: BulkReparseRequest,  # document_ids + optional new parser_config
):
    """Re-parse multiple documents. Deletes existing chunks, creates new tasks."""

@router.get("/knowledge-bases/{kb_id}/documents/status-summary")
async def document_status_summary(kb_id: UUID) -> DocStatusSummaryResponse:
    """Count of docs by status: {pending: 5, processing: 2, completed: 120, failed: 1}"""
```

### 2.3 Pydantic Models

```python
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum

class ParserConfig(BaseModel):
    chunk_token_size: int = Field(512, ge=64, le=4096)
    chunk_overlap_percent: int = Field(10, ge=0, le=50)
    delimiter: str = Field("\n", max_length=10)
    use_layout_detection: bool = True
    auto_keywords: int = Field(0, ge=0, le=10)
    auto_questions: int = Field(0, ge=0, le=10)
    page_ranges: Optional[list[tuple[int, int]]] = None

class MetadataFieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DATE = "date"
    ENUM = "enum"
    BOOLEAN = "boolean"

class MetadataFieldDef(BaseModel):
    type: MetadataFieldType
    required: bool = False
    description: Optional[str] = None
    values: Optional[list[str]] = None  # For enum type
    default: Optional[str] = None

class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    embedding_model: str = "openai/text-embedding-3-small"
    parser_config: ParserConfig = ParserConfig()
    metadata_schema: dict[str, MetadataFieldDef] = {}

class KBStatsResponse(BaseModel):
    kb_id: UUID
    document_count: int
    documents_by_status: dict[str, int]
    documents_by_type: dict[str, int]
    chunk_count: int
    active_chunk_count: int
    inactive_chunk_count: int
    total_tokens: int
    avg_tokens_per_chunk: float
    tag_count: int
    top_tags: list[dict]  # [{name, count}, ...]
```

### 2.4 UI Wireframes

#### Knowledge Base Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  Knowledge Bases                            [+ Create KB]   │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │ 📚 Technical Docs    │  │ 📚 HR Policies       │        │
│  │                      │  │                      │        │
│  │ 245 docs │ 12.4K     │  │ 67 docs │ 3.2K      │        │
│  │ chunks               │  │ chunks               │        │
│  │                      │  │                      │        │
│  │ ████████████░░ 92%   │  │ ████████████████ 100%│        │
│  │ parsed               │  │ parsed               │        │
│  │                      │  │                      │        │
│  │ Model: BGE-M3        │  │ Model: text-embed-3  │        │
│  │ [Open] [Settings]    │  │ [Open] [Settings]    │        │
│  └──────────────────────┘  └──────────────────────┘        │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │ 📚 Legal Compliance  │  │ ➕ Add Knowledge Base │        │
│  │ 23 docs │ 890 chunks │  │                      │        │
│  │                      │  │ Create a new KB to   │        │
│  │ ████████░░░░░░ 54%   │  │ start organizing     │        │
│  │ parsed (2 failed)    │  │ your documents       │        │
│  └──────────────────────┘  └──────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

#### KB Detail Page — Document Management

```
┌─────────────────────────────────────────────────────────────┐
│  Technical Docs > Documents                                 │
│                                                             │
│  [Upload Files ↑] [Bulk Reparse ⟳] [Filter ▾] [Sort ▾]    │
│                                                             │
│  Status: All(245) Completed(230) Processing(8) Failed(7)    │
│                                                             │
│  ┌─────┬────────────────────┬────────┬────────┬───────────┐│
│  │ ☐   │ Name               │ Chunks │ Status │ Updated   ││
│  ├─────┼────────────────────┼────────┼────────┼───────────┤│
│  │ ☐   │ 📄 Safety_Guide.pdf│   47   │ ✅ Done│ 2h ago    ││
│  │ ☐   │ 📊 Budget_2024.xlsx│   120  │ ✅ Done│ 1d ago    ││
│  │ ☐   │ 📄 API_Spec_v3.pdf │   --   │ ⏳ 67%│ now       ││
│  │ ☐   │ 📝 Release_Notes.md│   23   │ ✅ Done│ 3d ago    ││
│  │ ☐   │ 📄 Compliance.pdf  │   --   │ ❌ Fail│ 5h ago    ││
│  │     │   Error: OCR timeout│        │ [Retry]│           ││
│  └─────┴────────────────────┴────────┴────────┴───────────┘│
│                                                             │
│  [< Prev] Page 1 of 13 [Next >]                            │
└─────────────────────────────────────────────────────────────┘
```

#### KB Settings Page

```
┌─────────────────────────────────────────────────────────────┐
│  Technical Docs > Settings                                  │
│                                                             │
│  ┌── General ──────────────────────────────────────────────┐│
│  │ Name: [Technical Docs                            ]      ││
│  │ Description: [Engineering documentation and specs]      ││
│  │ Embedding Model: BGE-M3 (768-dim) 🔒 (locked)         ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌── Default Parser Config ────────────────────────────────┐│
│  │ Chunk Size: [512  ] tokens                              ││
│  │ Overlap:    [10   ] %                                   ││
│  │ Delimiter:  [\n   ]                                     ││
│  │ Layout Detection: [✓]                                   ││
│  │ Auto Keywords:    [3 ] per chunk                        ││
│  │ Auto Questions:   [0 ] per chunk                        ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌── Custom Metadata Fields ───────────────────────────────┐│
│  │ department    │ string  │ required │ [Edit] [Delete]    ││
│  │ classification│ enum    │ optional │ [Edit] [Delete]    ││
│  │   values: public, internal, confidential                ││
│  │ [+ Add Field]                                           ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌── Tags ─────────────────────────────────────────────────┐│
│  │ safety (47 chunks) [Rename] [Delete]                    ││
│  │ deprecated (12 chunks) [Rename] [Delete]                ││
│  │ reviewed (198 chunks) [Rename] [Delete]                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌── Danger Zone ──────────────────────────────────────────┐│
│  │ [Archive KB]  [Delete All Chunks]  [Delete KB]          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 2.5 Improvements Over RAGFlow

1. **Metadata Schema at KB Level**: RAGFlow stores metadata loosely. We enforce a schema with types and validation — consistent metadata across all chunks in a KB.

2. **Tag Management as First-Class Feature**: RAGFlow tags are free-form keywords. We use normalized tag tables with colors, counts, and bulk operations.

3. **Embedding Model Lock**: Once a KB has indexed chunks, the embedding model is locked. RAGFlow allows (dangerous) model changes that silently break vector compatibility.

4. **Document Processing Status Aggregation**: Single endpoint returns status breakdown. RAGFlow requires querying all documents individually.

5. **Bulk Operations**: Bulk reparse, bulk tag, bulk toggle. RAGFlow processes individually.

6. **Archived State**: Soft-delete with archive status. RAGFlow has binary active/deleted.

7. **Parser Config Inheritance**: KB default → document override, with Pydantic validation at both levels.
