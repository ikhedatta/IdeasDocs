"""Embedding interface — abstract hook for vector generation.

Phase 5: This is an interface-only module in the POC. Implement a
concrete subclass to plug in any embedding model.

RAGFlow supports: BuiltinEmbed (TEI), OpenAI, Azure, Jina, etc.
with batch processing and title-content weighted vectors.
"""

from __future__ import annotations

import abc
from typing import Optional

from models import Chunk


class BaseEmbedder(abc.ABC):
    """Abstract embedding interface.

    Implement `embed_batch` to integrate with any embedding provider.
    The pipeline calls `embed_chunks` which handles batching.
    """

    @abc.abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (same order as input).
        """

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""

    def embed_chunks(
        self,
        chunks: list[Chunk],
        batch_size: int = 16,
    ) -> list[Chunk]:
        """Embed all chunks, populating the `embedding` field.

        Processes in batches for efficiency.
        """
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.content for c in batch]
            vectors = self.embed_batch(texts)
            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector
        return chunks


class NoOpEmbedder(BaseEmbedder):
    """No-op embedder for testing — returns zero vectors."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dim for _ in texts]


# ── Example concrete implementations (uncomment to use) ───────────
#
# class OpenAIEmbedder(BaseEmbedder):
#     """OpenAI text-embedding-3-small integration."""
#
#     def __init__(self, model: str = "text-embedding-3-small", api_key: str = ""):
#         import openai
#         self._client = openai.OpenAI(api_key=api_key)
#         self._model = model
#         self._dim = 1536  # text-embedding-3-small default
#
#     @property
#     def dimension(self) -> int:
#         return self._dim
#
#     def embed_batch(self, texts: list[str]) -> list[list[float]]:
#         response = self._client.embeddings.create(input=texts, model=self._model)
#         return [item.embedding for item in response.data]
#
#
# class SentenceTransformerEmbedder(BaseEmbedder):
#     """Local sentence-transformers model."""
#
#     def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
#         from sentence_transformers import SentenceTransformer
#         self._model = SentenceTransformer(model_name)
#         self._dim = self._model.get_sentence_embedding_dimension()
#
#     @property
#     def dimension(self) -> int:
#         return self._dim
#
#     def embed_batch(self, texts: list[str]) -> list[list[float]]:
#         embeddings = self._model.encode(texts, convert_to_numpy=True)
#         return embeddings.tolist()
