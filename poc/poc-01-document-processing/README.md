# POC-01: Document Processing Pipeline

## Feature
**Multi-format document parsing → intelligent chunking → embedding → vector storage**

This is the foundational POC that implements RAGFlow's core insight: **documents are not flat text — they have structure (headers, tables, images, paragraphs) that must be preserved during chunking.**

## What Problem It Solves
Most RAG systems naively split documents by character count, destroying semantic boundaries. This POC demonstrates:
1. **Format-aware parsing** — Extract structured content blocks (text, tables, headers) from PDF, DOCX, HTML, Markdown
2. **Token-budget chunking** — Split by delimiters first, then merge to token budget with configurable overlap
3. **Table/image context windows** — Tables get surrounding text for context
4. **Embedding & storage** — Batch embed chunks and store in Qdrant with rich metadata
5. **Content-hash deduplication** — Skip re-processing unchanged documents

## Key RAGFlow Patterns Implemented
- **Parser Registry** (`deepdoc/parser/`) — Format-specific parsers behind a common interface
- **TokenChunker** (`rag/flow/chunker/token_chunker.py`) — Delimiter-split → token-merge → overlap
- **Task deduplication** (`api/db/services/task_service.py`) — xxhash64 digest of config
- **Batch embedding** — Process chunks in batches of 32

## Architecture

```
Input File (PDF/DOCX/HTML/MD)
    │
    ▼ ParserRegistry.parse()
List[ContentBlock]  (type-annotated structured blocks)
    │
    ▼ TokenChunker.chunk()
List[Chunk]  (token-budget chunks with metadata)
    │
    ▼ EmbeddingService.embed_batch()
List[Chunk + Vector]
    │
    ▼ QdrantStore.upsert()
Qdrant Collection (dense + sparse vectors + payload)
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | CLI demo + FastAPI endpoints |
| `parsers/base.py` | Parser protocol and registry |
| `parsers/pdf_parser.py` | PDF parsing with layout handling |
| `parsers/docx_parser.py` | DOCX structured extraction |
| `parsers/html_parser.py` | HTML with boilerplate removal |
| `parsers/markdown_parser.py` | Markdown section splitting |
| `chunkers/token_chunker.py` | Token-budget chunking with overlap |
| `chunkers/models.py` | Data models (ContentBlock, Chunk, ChunkConfig) |
| `embedding_service.py` | Batch embedding via litellm |
| `qdrant_store.py` | Qdrant collection management and upsert |
| `pipeline.py` | Orchestrates parse → chunk → embed → store |

## How to Run

```bash
# 1. Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 2. Set env vars
export OPENAI_API_KEY="sk-..."
# OR for Ollama:
# export EMBEDDING_MODEL="ollama/nomic-embed-text"
# export LLM_BASE_URL="http://localhost:11434"

# 3. Run CLI demo
python main.py --file sample.pdf --kb-id my-knowledge-base

# 4. Or run as API
uvicorn main:app --reload --port 8001
# POST /process with multipart file upload
```

## How to Extend Into Full Platform

1. **Add more parsers**: Register new parsers in `parsers/` for PPTX, Excel, email, code files
2. **Add layout detection**: Integrate `unstructured.io` or PyMuPDF's layout analysis for better PDF parsing
3. **Add async task queue**: Wrap `pipeline.process()` in a Celery task for background processing
4. **Add progress tracking**: Emit progress events via Redis pub/sub or SSE
5. **Add metadata extraction**: Use LLM to extract custom metadata fields from chunks
6. **Add auto-keywords**: Post-chunking LLM call to generate searchable keywords per chunk
7. **Wire to POC-02**: Feed the Qdrant collection into hybrid retrieval
