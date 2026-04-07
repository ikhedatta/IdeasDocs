# POC-03: Citation-Enforced RAG

## Feature
**Retrieve → Format Context → Generate with citations → Validate citations → Return with references**

This is the "R" in RAG done right. The system ensures the LLM **only** answers from approved content and every claim includes a traceable citation back to the source chunk.

## What Problem It Solves
- **Hallucination**: LLMs fabricate facts. Citation enforcement forces answers to be grounded in retrieved content
- **Traceability**: Users need to verify AI answers against source documents
- **Controlled knowledge**: In enterprise settings, the AI should NOT be the knowledge source — approved content is
- **Empty response handling**: When no relevant content is found, the system must admit "I don't know" instead of guessing

## Key RAGFlow Patterns Implemented
- **Citation prompt template** (`rag/prompts/citation_prompt.md` — system instructions forcing `[n]` notation)
- **Context formatting** (`rag/prompts/generator.py` — `kb_prompt()` numbered chunk formatting)
- **Empty response protocol** (fallback when no chunks pass threshold)
- **Citation extraction** (post-processing to validate and extract `[n]` references from LLM output)
- **Multi-provider LLM** (`rag/llm/chat_model.py` — litellm-based abstraction)

## Architecture

```
User Question
    │
    ▼
Hybrid Retrieval (POC-02)
    │
    ▼
Context Assembly
    ├── Number chunks [1], [2], ...
    ├── Include source metadata
    └── Respect token budget
    │
    ▼
LLM Generation (litellm)
    ├── System: "Answer ONLY from context, cite using [n]"
    ├── Context: "[1] chunk text...\n[2] chunk text..."
    └── Query: user question
    │
    ▼
Citation Post-Processing
    ├── Extract [n] references from response
    ├── Map to source documents
    ├── Flag uncited claims (optional)
    └── Build response with reference list
    │
    ▼
Structured Response
    ├── answer: "The policy states X [1] and Y [2]..."
    ├── citations: [{index: 1, doc: "policy.pdf", chunk: "...", score: 0.89}]
    └── confidence: "grounded" | "partial" | "no_context"
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server + CLI |
| `rag_pipeline.py` | Full RAG orchestrator (retrieve → generate → cite) |
| `prompt_templates.py` | System prompts for citation enforcement |
| `citation_extractor.py` | Parse and validate citations from LLM output |
| `llm_client.py` | litellm wrapper with streaming support |

## How to Run

```bash
# Prerequisites: Qdrant + indexed documents (via POC-01)
export OPENAI_API_KEY="sk-..."

# Run server
uvicorn main:app --reload --port 8003

# Ask a question:
# POST /ask {"question": "What is the fire safety protocol?", "kb_ids": ["my-kb"]}
```

## How to Extend

1. **Streaming**: Add SSE endpoint that streams answer tokens as they arrive
2. **Multi-turn chat**: Add conversation history to the prompt
3. **Citation highlighting**: Return character offsets in source for UI highlighting
4. **Confidence scoring**: Score answer confidence based on citation coverage
5. **Wire to POC-02**: Uses the retrieval engine, wire to POC-04 for chunk management
