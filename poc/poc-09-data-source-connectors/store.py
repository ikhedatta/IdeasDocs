"""JSON-backed connector store — swap for PostgreSQL / Redis in production."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from credentials import decrypt_credentials, encrypt_credentials, mask_credentials
from models import ConnectorConfig, ConnectorStatus, SourceType


class ConnectorStore:
    """Persistent storage for connector configurations (JSON file for POC)."""

    def __init__(self, data_dir: str = "./data") -> None:
        self._dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._file = os.path.join(data_dir, "connectors.json")
        self._data: dict[str, dict] = {}
        self._load()

    # ── CRUD ───────────────────────────────────────────────────────

    def create(self, config: ConnectorConfig) -> ConnectorConfig:
        raw = config.model_dump(mode="json")
        # Encrypt credentials before storage
        raw["_encrypted_creds"] = encrypt_credentials(raw.pop("credentials", {}))
        raw["credentials"] = {}  # Don't store plaintext
        self._data[config.id] = raw
        self._save()
        return config

    def get(self, connector_id: str) -> Optional[ConnectorConfig]:
        raw = self._data.get(connector_id)
        if raw is None:
            return None
        copy = dict(raw)
        # Decrypt credentials
        copy["credentials"] = decrypt_credentials(copy.pop("_encrypted_creds", ""))
        return ConnectorConfig(**copy)

    def get_masked(self, connector_id: str) -> Optional[dict]:
        """Return connector with masked credentials for API responses."""
        raw = self._data.get(connector_id)
        if raw is None:
            return None
        copy = dict(raw)
        creds = decrypt_credentials(copy.pop("_encrypted_creds", ""))
        copy["credentials"] = mask_credentials(creds)
        return copy

    def list_all(self, source_type: Optional[SourceType] = None) -> list[dict]:
        results = []
        for cid, raw in self._data.items():
            if source_type and raw.get("source_type") != source_type.value:
                continue
            copy = dict(raw)
            creds = decrypt_credentials(copy.pop("_encrypted_creds", ""))
            copy["credentials"] = mask_credentials(creds)
            results.append(copy)
        return results

    def update(self, connector_id: str, updates: dict) -> Optional[ConnectorConfig]:
        raw = self._data.get(connector_id)
        if raw is None:
            return None

        if "credentials" in updates and updates["credentials"]:
            raw["_encrypted_creds"] = encrypt_credentials(updates.pop("credentials"))

        for k, v in updates.items():
            if v is not None and k != "_encrypted_creds":
                raw[k] = v

        raw["updated_at"] = datetime.utcnow().isoformat()
        self._data[connector_id] = raw
        self._save()

        # Return full config
        copy = dict(raw)
        copy["credentials"] = decrypt_credentials(copy.pop("_encrypted_creds", ""))
        return ConnectorConfig(**copy)

    def delete(self, connector_id: str) -> bool:
        if connector_id in self._data:
            del self._data[connector_id]
            self._save()
            return True
        return False

    # ── Persistence ────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self._file):
            with open(self._file, "r") as f:
                self._data = json.load(f)

    def _save(self) -> None:
        with open(self._file, "w") as f:
            json.dump(self._data, f, indent=2, default=str)
