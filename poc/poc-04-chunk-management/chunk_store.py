"""Chunk store: Qdrant operations for chunk CRUD.

Implements the data layer for chunk management:
- List/scroll with filters (KB, document, status, keyword)
- Get single chunk by ID
- Create (upsert with new vector)
- Update (re-embed + upsert)
- Toggle active/inactive (payload update only, no re-embed)
- Delete (hard delete from Qdrant)
"""
import logging
import uuid
from datetime import datetime, timezone

import tiktoken
from qdrant_client import QdrantClient, models

logger = logging.getLogger(__name__)


class ChunkStore:
    """Qdrant-backed chunk storage with CRUD operations."""

    def __init__(self, qdrant_url: str = "http://localhost:6333"):
        self.client = QdrantClient(url=qdrant_url)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None

    def _collection_name(self, kb_id: str) -> str:
        return f"kb_{kb_id}"

    def _count_tokens(self, text: str) -> int:
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return len(text.split())

    def list_chunks(
        self,
        kb_id: str,
        document_id: str | None = None,
        status: str = "all",
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """List chunks with filtering and pagination.

        Returns:
            (chunks, total_count)
        """
        collection = self._collection_name(kb_id)

        # Build filter conditions
        must_conditions = []
        if document_id:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=document_id)
                )
            )
        if status == "active":
            must_conditions.append(
                models.FieldCondition(
                    key="is_active", match=models.MatchValue(value=True)
                )
            )
        elif status == "inactive":
            must_conditions.append(
                models.FieldCondition(
                    key="is_active", match=models.MatchValue(value=False)
                )
            )

        query_filter = models.Filter(must=must_conditions) if must_conditions else None

        # Get total count
        count_result = self.client.count(
            collection_name=collection, count_filter=query_filter, exact=True
        )
        total = count_result.count

        # Scroll with offset
        offset = (page - 1) * page_size

        # Use scroll for paginated results
        points, _next = self.client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            limit=page_size,
            offset=offset if offset > 0 else None,
            with_payload=True,
        )

        # If keyword filter, do it in-memory (for simple keyword search)
        chunks = []
        for point in points:
            payload = point.payload or {}
            content = payload.get("content", "")

            if keyword and keyword.lower() not in content.lower():
                continue

            chunks.append(
                {
                    "chunk_id": str(point.id),
                    "content": content,
                    "document_id": payload.get("document_id", ""),
                    "document_name": payload.get("document_name", ""),
                    "kb_id": kb_id,
                    "chunk_order": payload.get("chunk_order", 0),
                    "is_active": payload.get("is_active", True),
                    "token_count": payload.get("token_count", 0),
                    "metadata": payload.get("metadata", {}),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                }
            )

        return chunks, total

    def get_chunk(self, kb_id: str, chunk_id: str) -> dict | None:
        """Get a single chunk by ID."""
        collection = self._collection_name(kb_id)
        try:
            points = self.client.retrieve(
                collection_name=collection,
                ids=[chunk_id],
                with_payload=True,
            )
            if not points:
                return None

            point = points[0]
            payload = point.payload or {}
            return {
                "chunk_id": str(point.id),
                "content": payload.get("content", ""),
                "document_id": payload.get("document_id", ""),
                "document_name": payload.get("document_name", ""),
                "kb_id": kb_id,
                "chunk_order": payload.get("chunk_order", 0),
                "is_active": payload.get("is_active", True),
                "token_count": payload.get("token_count", 0),
                "metadata": payload.get("metadata", {}),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
            }
        except Exception as e:
            logger.error(f"Failed to get chunk {chunk_id}: {e}")
            return None

    def create_chunk(
        self,
        kb_id: str,
        content: str,
        vector: list[float],
        document_id: str = "manual",
        document_name: str = "Manual Entry",
        metadata: dict | None = None,
    ) -> str:
        """Create a new chunk with embedding.

        Returns the new chunk ID.
        """
        collection = self._collection_name(kb_id)
        chunk_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "content": content,
            "document_id": document_id,
            "document_name": document_name,
            "kb_id": kb_id,
            "chunk_order": 0,
            "is_active": True,
            "token_count": self._count_tokens(content),
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

        self.client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=chunk_id,
                    vector={"dense": vector},
                    payload=payload,
                )
            ],
        )

        return chunk_id

    def update_chunk(
        self,
        kb_id: str,
        chunk_id: str,
        content: str,
        vector: list[float],
        metadata: dict | None = None,
    ) -> bool:
        """Update chunk content and re-embed.

        Returns True if successful.
        """
        collection = self._collection_name(kb_id)
        now = datetime.now(timezone.utc).isoformat()

        # Get existing payload to preserve fields
        existing = self.get_chunk(kb_id, chunk_id)
        if not existing:
            return False

        payload = {
            "content": content,
            "document_id": existing["document_id"],
            "document_name": existing["document_name"],
            "kb_id": kb_id,
            "chunk_order": existing["chunk_order"],
            "is_active": existing["is_active"],
            "token_count": self._count_tokens(content),
            "metadata": metadata if metadata is not None else existing.get("metadata", {}),
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }

        self.client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=chunk_id,
                    vector={"dense": vector},
                    payload=payload,
                )
            ],
        )

        return True

    def toggle_chunk(self, kb_id: str, chunk_id: str, is_active: bool) -> bool:
        """Toggle chunk active/inactive status (payload-only update, no re-embed)."""
        collection = self._collection_name(kb_id)
        now = datetime.now(timezone.utc).isoformat()

        try:
            self.client.set_payload(
                collection_name=collection,
                payload={"is_active": is_active, "updated_at": now},
                points=[chunk_id],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to toggle chunk {chunk_id}: {e}")
            return False

    def delete_chunk(self, kb_id: str, chunk_id: str) -> bool:
        """Hard delete a chunk from Qdrant."""
        collection = self._collection_name(kb_id)
        try:
            self.client.delete(
                collection_name=collection,
                points_selector=models.PointIdsList(points=[chunk_id]),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete chunk {chunk_id}: {e}")
            return False

    def batch_toggle(self, kb_id: str, chunk_ids: list[str], is_active: bool) -> tuple[int, list[str]]:
        """Toggle multiple chunks. Returns (success_count, errors)."""
        succeeded = 0
        errors = []
        for cid in chunk_ids:
            if self.toggle_chunk(kb_id, cid, is_active):
                succeeded += 1
            else:
                errors.append(f"Failed to toggle {cid}")
        return succeeded, errors

    def batch_delete(self, kb_id: str, chunk_ids: list[str]) -> tuple[int, list[str]]:
        """Delete multiple chunks. Returns (success_count, errors)."""
        collection = self._collection_name(kb_id)
        try:
            self.client.delete(
                collection_name=collection,
                points_selector=models.PointIdsList(points=chunk_ids),
            )
            return len(chunk_ids), []
        except Exception as e:
            return 0, [str(e)]
