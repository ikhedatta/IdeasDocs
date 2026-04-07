"""
Qdrant Store — vector storage with hybrid search support.

RAGFlow Source: common/doc_store/es_conn.py, common/doc_store/doc_store_base.py

RAGFlow stores vectors in Elasticsearch (dense_vector field). We use Qdrant
which provides native hybrid search (dense + sparse) without the Elasticsearch
operational overhead.

Key Pattern: Each Knowledge Base gets its own Qdrant collection, with both
dense and sparse vectors for hybrid retrieval.
"""

from typing import Optional
from uuid import uuid4
from qdrant_client import QdrantClient, models
from chunkers.models import Chunk


class QdrantStore:
    """
    Qdrant-based vector storage for document chunks.
    
    RAGFlow Insight: Each Knowledge Base has a separate index/collection.
    This provides tenant isolation and allows different embedding dimensions
    per KB. Collections include both dense vectors (semantic) and sparse
    vectors (BM25-style keyword matching) for hybrid search.
    """

    def __init__(self, url: str = "http://localhost:6333"):
        self.client = QdrantClient(url=url)

    def create_collection(
        self,
        collection_name: str,
        dimension: int = 1536,
        recreate: bool = False,
    ):
        """
        Create a Qdrant collection for a Knowledge Base.
        
        RAGFlow Pattern: Collections have both dense and sparse vectors
        for hybrid search. Dense for semantic matching, sparse for
        keyword/BM25-style matching.
        """
        if recreate:
            try:
                self.client.delete_collection(collection_name)
            except Exception:
                pass

        # Check if collection already exists
        try:
            self.client.get_collection(collection_name)
            return  # Already exists
        except Exception:
            pass

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=dimension,
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
        # RAGFlow Pattern: Indexed fields for fast KB/document filtering
        for field_name, schema_type in [
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("kb_id", models.PayloadSchemaType.KEYWORD),
            ("is_active", models.PayloadSchemaType.BOOL),
            ("document_name", models.PayloadSchemaType.KEYWORD),
            ("chunk_order", models.PayloadSchemaType.FLOAT),
        ]:
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type,
            )

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: list[Chunk],
        document_id: str,
        document_name: str,
        kb_id: str,
    ) -> int:
        """
        Upsert chunks with dense vectors into Qdrant.
        
        RAGFlow Pattern (from common/doc_store/es_conn.py):
        - Bulk upsert for efficiency (batch of 64 in RAGFlow)
        - Rich payload with metadata for filtering and display
        - available_int field (we use is_active) for soft disable
        
        Returns: number of chunks upserted
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            if chunk.embedding is None:
                continue

            point_id = chunk.id
            points.append(models.PointStruct(
                id=point_id,
                vector={
                    "dense": chunk.embedding,
                },
                payload={
                    "document_id": document_id,
                    "kb_id": kb_id,
                    "document_name": document_name,
                    "content": chunk.text,
                    "content_tokens": chunk.token_count,
                    "chunk_order": chunk.chunk_order,
                    "is_active": True,
                    "source_pages": chunk.source_pages,
                    "source_positions": chunk.source_positions,
                    "block_types": chunk.block_types,
                    "metadata": chunk.metadata,
                },
            ))

        # Batch upsert (Qdrant handles batching internally)
        if points:
            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )

        return len(points)

    def delete_by_document(self, collection_name: str, document_id: str):
        """
        Delete all chunks for a document.
        
        RAGFlow Pattern: When re-parsing, delete old chunks first.
        """
        self.client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                    ],
                ),
            ),
        )

    def get_collection_info(self, collection_name: str) -> dict:
        """Get collection stats (point count, etc.)."""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            return {"name": collection_name, "error": str(e)}
