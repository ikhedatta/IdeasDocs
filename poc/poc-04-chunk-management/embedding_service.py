"""Embedding service for chunk creation and re-embedding."""
import logging

import litellm

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embed text for Qdrant storage using litellm."""

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._dimension: int | None = None

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        resp = await litellm.aembedding(model=self.model, input=[text])
        vector = resp.data[0]["embedding"]
        if self._dimension is None:
            self._dimension = len(vector)
        return vector

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed multiple texts in batches."""
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await litellm.aembedding(model=self.model, input=batch)
            vectors = [d["embedding"] for d in resp.data]
            all_vectors.extend(vectors)
            if self._dimension is None and vectors:
                self._dimension = len(vectors[0])
        return all_vectors

    @property
    def dimension(self) -> int:
        return self._dimension or 1536
