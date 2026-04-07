"""
Embedding Service — batch embedding via litellm.

RAGFlow Source: rag/llm/embedding_model.py

RAGFlow abstracts 20+ embedding providers behind a factory pattern.
This POC uses litellm which provides the same multi-provider support
with less custom code.

Key Pattern: Batch embedding (32 texts/call) to minimize API latency.
"""

import os
import asyncio
from typing import Optional
import litellm


class EmbeddingService:
    """
    Batch embedding service using litellm for multi-provider support.
    
    Supports: OpenAI, Cohere, HuggingFace, Ollama, Azure, Bedrock, etc.
    
    RAGFlow Insight: Embeddings are generated in batches (default 32)
    to minimize API round-trips. The embedding model is locked per
    Knowledge Base — changing models requires re-indexing all chunks.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        batch_size: int = 32,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.batch_size = batch_size
        self.dimension: Optional[int] = None
        
        # Configure litellm
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        if base_url:
            litellm.api_base = base_url

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        result = await litellm.aembedding(model=self.model, input=[text])
        vector = result.data[0]["embedding"]
        if self.dimension is None:
            self.dimension = len(vector)
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts in batches.
        
        RAGFlow Pattern (from embedding_model.py):
        - Process in batches of batch_size to avoid API limits
        - Return vectors in same order as input texts
        """
        all_vectors: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # Filter empty texts (replace with placeholder)
            clean_batch = [t if t.strip() else "empty" for t in batch]
            
            result = await litellm.aembedding(model=self.model, input=clean_batch)
            
            batch_vectors = [item["embedding"] for item in result.data]
            all_vectors.extend(batch_vectors)
            
            # Track dimension from first result
            if self.dimension is None and batch_vectors:
                self.dimension = len(batch_vectors[0])

        return all_vectors

    def embed_sync(self, text: str) -> list[float]:
        """Synchronous single-text embedding (for CLI usage)."""
        result = litellm.embedding(model=self.model, input=[text])
        vector = result.data[0]["embedding"]
        if self.dimension is None:
            self.dimension = len(vector)
        return vector

    def embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous batch embedding (for CLI usage)."""
        return asyncio.get_event_loop().run_until_complete(self.embed_batch(texts))

    def get_dimension(self) -> int:
        """Get embedding dimension (available after first embed call)."""
        if self.dimension is None:
            # Probe with a test embedding
            self.embed_sync("test")
        return self.dimension
