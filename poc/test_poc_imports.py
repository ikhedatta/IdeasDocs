"""
Import smoke-tests for POC-01 through POC-06.

For each POC, adds its directory to sys.path and verifies that key
modules can be imported without errors. Does NOT start servers or
connect to external services — only checks that source files parse
and all intra-POC imports resolve.

Run:  python -m pytest test_poc_imports.py -v
"""

import importlib
import sys
from pathlib import Path

import pytest

POC_ROOT = Path(__file__).resolve().parent

# (poc_directory_name, list_of_modules_to_import)
POC_MODULES = [
    # POC-01: Document Processing Pipeline
    (
        "poc-01-document-processing",
        [
            "chunkers",             # package: models, token_chunker
            "parsers",              # package: base, pdf, docx, html, markdown
            "embedding_service",    # EmbeddingService (litellm)
            "qdrant_store",         # QdrantStore (qdrant_client)
            "pipeline",            # DocumentPipeline (orchestrator)
            "main",                # FastAPI app
        ],
    ),
    # POC-02: Hybrid Retrieval
    (
        "poc-02-hybrid-retrieval",
        [
            "config",              # RetrievalConfig, FusionMethod, SearchResult
            "sparse_encoder",      # SparseEncoder (stdlib only)
            "context_builder",     # ContextBuilder (tiktoken)
            "reranker",            # Reranker (httpx)
            "retriever",           # HybridRetriever (qdrant, litellm)
            "main",                # FastAPI app
        ],
    ),
    # POC-03: Citation RAG
    (
        "poc-03-citation-rag",
        [
            "prompt_templates",    # System prompts (stdlib only)
            "citation_extractor",  # CitationExtractor (stdlib only)
            "llm_client",         # LLMClient (litellm)
            "rag_pipeline",       # RAGPipeline (qdrant, litellm)
            "main",                # FastAPI app
        ],
    ),
    # POC-04: Chunk Management
    (
        "poc-04-chunk-management",
        [
            "models",              # Pydantic request/response models
            "embedding_service",   # EmbeddingService (litellm)
            "chunk_store",         # ChunkStore (qdrant, tiktoken)
            "main",                # FastAPI app
        ],
    ),
    # POC-05: Retrieval Debugger
    (
        "poc-05-retrieval-debugger",
        [
            "models",              # Pydantic request/response models
            "debugger",            # RetrievalDebugger (qdrant, litellm)
            "test_suite",          # TestSuiteRunner
            "main",                # FastAPI app
        ],
    ),
    # POC-06: Knowledge Base Manager
    (
        "poc-06-knowledge-base-manager",
        [
            "models",              # Pydantic models
            "kb_store",            # KBStore (json file-backed)
            "main",                # FastAPI app
        ],
    ),
]


def _build_test_ids():
    """Generate human-readable test IDs like 'poc-01/main'."""
    ids = []
    for poc_dir, modules in POC_MODULES:
        for mod in modules:
            ids.append(f"{poc_dir}/{mod}")
    return ids


def _build_params():
    """Flatten POC_MODULES into (poc_dir, module_name) pairs."""
    params = []
    for poc_dir, modules in POC_MODULES:
        for mod in modules:
            params.append((poc_dir, mod))
    return params


@pytest.mark.parametrize(
    "poc_dir,module_name",
    _build_params(),
    ids=_build_test_ids(),
)
def test_poc_import(poc_dir: str, module_name: str):
    """Verify that a POC module imports without errors.

    Strategy:
    1. Temporarily prepend the POC directory to sys.path
    2. Import the module (clearing any stale cache first)
    3. Restore sys.path regardless of outcome
    """
    poc_path = str(POC_ROOT / poc_dir)
    inserted = False

    # Ensure the POC directory is on sys.path
    if poc_path not in sys.path:
        sys.path.insert(0, poc_path)
        inserted = True

    try:
        # Remove from module cache so each POC gets a clean import
        # (some POCs have modules with the same name, e.g. "models")
        if module_name in sys.modules:
            del sys.modules[module_name]

        mod = importlib.import_module(module_name)
        assert mod is not None, f"import_module returned None for {module_name}"
    finally:
        # Clean up: remove from path and module cache to avoid
        # cross-contamination between POCs with same-named modules
        if inserted and poc_path in sys.path:
            sys.path.remove(poc_path)
        if module_name in sys.modules:
            del sys.modules[module_name]
