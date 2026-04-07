"""Knowledge base metadata store.

JSON file-based for POC simplicity. In production, replace with
PostgreSQL + SQLAlchemy (schema is shaped for easy migration).
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from models import DocumentStatus, ParserConfig

logger = logging.getLogger(__name__)


class KBStore:
    """File-backed KB and document metadata store."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.kb_file = self.data_dir / "knowledge_bases.json"
        self.doc_file = self.data_dir / "documents.json"
        self._kbs = self._load(self.kb_file)
        self._docs = self._load(self.doc_file)

    def _load(self, path: Path) -> dict:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_kbs(self):
        with open(self.kb_file, "w", encoding="utf-8") as f:
            json.dump(self._kbs, f, indent=2, default=str)

    def _save_docs(self):
        with open(self.doc_file, "w", encoding="utf-8") as f:
            json.dump(self._docs, f, indent=2, default=str)

    # --- KB Operations ---

    def create_kb(self, name: str, description: str, parser_config: dict, tags: list[str]) -> dict:
        kb_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        kb = {
            "id": kb_id,
            "name": name,
            "description": description,
            "parser_config": parser_config,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
        }
        self._kbs[kb_id] = kb
        self._save_kbs()
        return kb

    def get_kb(self, kb_id: str) -> dict | None:
        return self._kbs.get(kb_id)

    def list_kbs(self) -> list[dict]:
        kbs = list(self._kbs.values())
        # Add document counts
        for kb in kbs:
            kb["document_count"] = len(self.list_documents(kb["id"]))
        return kbs

    def update_kb(self, kb_id: str, updates: dict) -> dict | None:
        kb = self._kbs.get(kb_id)
        if not kb:
            return None
        for key, value in updates.items():
            if value is not None:
                kb[key] = value
        kb["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_kbs()
        return kb

    def delete_kb(self, kb_id: str) -> bool:
        if kb_id not in self._kbs:
            return False
        del self._kbs[kb_id]
        # Delete associated documents
        to_delete = [did for did, doc in self._docs.items() if doc.get("kb_id") == kb_id]
        for did in to_delete:
            del self._docs[did]
        self._save_kbs()
        self._save_docs()
        return True

    # --- Document Operations ---

    def add_document(
        self, kb_id: str, name: str, file_type: str, file_size: int = 0
    ) -> dict:
        doc_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": doc_id,
            "kb_id": kb_id,
            "name": name,
            "file_type": file_type,
            "file_size": file_size,
            "status": DocumentStatus.QUEUED.value,
            "chunk_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        self._docs[doc_id] = doc
        self._save_docs()
        return doc

    def get_document(self, doc_id: str) -> dict | None:
        return self._docs.get(doc_id)

    def list_documents(self, kb_id: str) -> list[dict]:
        return [d for d in self._docs.values() if d.get("kb_id") == kb_id]

    def update_document_status(
        self, doc_id: str, status: str, chunk_count: int | None = None, error: str | None = None
    ) -> dict | None:
        doc = self._docs.get(doc_id)
        if not doc:
            return None
        doc["status"] = status
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        if chunk_count is not None:
            doc["chunk_count"] = chunk_count
        if error is not None:
            doc["error_message"] = error
        self._save_docs()
        return doc

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self._docs:
            return False
        del self._docs[doc_id]
        self._save_docs()
        return True

    def get_kb_stats(self, kb_id: str) -> dict:
        """Compute aggregate statistics for a knowledge base."""
        kb = self.get_kb(kb_id)
        if not kb:
            return {}

        docs = self.list_documents(kb_id)
        status_counts: dict[str, int] = {}
        total_chunks = 0

        for doc in docs:
            status = doc.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            total_chunks += doc.get("chunk_count", 0)

        return {
            "kb_id": kb_id,
            "kb_name": kb.get("name", ""),
            "document_count": len(docs),
            "documents_by_status": status_counts,
            "chunk_count": total_chunks,
            "active_chunks": total_chunks,  # Detailed count requires Qdrant query
            "inactive_chunks": 0,
            "estimated_tokens": total_chunks * 256,  # Rough estimate
        }
