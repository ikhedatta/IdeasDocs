"""Google Cloud Storage connector — ingest objects from GCS buckets."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Generator, Optional

from interfaces import BaseConnector, BrowsableConnector, LoadConnector, PollConnector
from models import (
    AuthMethod,
    ConnectorConfig,
    ContentItem,
    ContentListResponse,
    SourceDocument,
    SourceInfo,
    SourceType,
    SyncCheckpoint,
)
from registry import register

logger = logging.getLogger(__name__)

GCS_API = "https://storage.googleapis.com/storage/v1"


@register(SourceType.GCS)
class GCSConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest files from Google Cloud Storage buckets."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.GCS,
            display_name="Google Cloud Storage",
            description="Sync objects from GCS buckets using service account or OAuth.",
            icon="database",
            category="cloud_storage",
            auth_methods=[AuthMethod.SERVICE_ACCOUNT, AuthMethod.OAUTH2],
            default_auth=AuthMethod.SERVICE_ACCOUNT,
            config_schema={
                "bucket": {"type": "string", "required": True},
                "prefix": {"type": "string", "default": ""},
                "file_extensions": {"type": "array", "items": "string"},
                "max_file_mb": {"type": "number", "default": 100},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._bucket = cfg["bucket"]
        self._prefix = cfg.get("prefix", "")
        self._extensions = set(cfg.get("file_extensions", []))
        self._max_bytes = cfg.get("max_file_mb", 100) * 1024 * 1024

        # Use access token (from OAuth or service account exchange)
        token = creds.get("access_token", "")
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get(f"{GCS_API}/b/{self._bucket}")
            return r.status_code == 200
        except Exception:
            return False

    def _should_include(self, name: str) -> bool:
        if not self._extensions:
            return True
        return any(name.lower().endswith(f".{ext}") for ext in self._extensions)

    async def _list_objects(self, page_token: str = "") -> dict:
        params: dict[str, Any] = {"prefix": self._prefix, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        r = await self._client.get(f"{GCS_API}/b/{self._bucket}/o", params=params)
        r.raise_for_status()
        return r.json()

    async def _download_object(self, name: str) -> bytes:
        import urllib.parse
        encoded = urllib.parse.quote(name, safe="")
        r = await self._client.get(f"{GCS_API}/b/{self._bucket}/o/{encoded}", params={"alt": "media"})
        r.raise_for_status()
        return r.content

    def _obj_to_doc(self, obj: dict, content: bytes) -> SourceDocument:
        name = obj.get("name", "")
        filename = name.split("/")[-1]
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        return SourceDocument(
            source_id=f"{self._bucket}/{name}",
            source_type=SourceType.GCS,
            connector_id=self.config.id,
            title=filename,
            content=content,
            extension=ext,
            mime_type=obj.get("contentType", "application/octet-stream"),
            size_bytes=int(obj.get("size", len(content))),
            url=f"gs://{self._bucket}/{name}",
            updated_at=obj.get("updated"),
            metadata={"bucket": self._bucket, "name": name, "generation": obj.get("generation")},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        page_token = ""
        while True:
            data = await self._list_objects(page_token)
            items = data.get("items", [])
            if not items:
                break
            batch: list[SourceDocument] = []
            for obj in items:
                name = obj.get("name", "")
                if not self._should_include(name):
                    continue
                if int(obj.get("size", 0)) > self._max_bytes:
                    continue
                try:
                    content = await self._download_object(name)
                    batch.append(self._obj_to_doc(obj, content))
                except Exception as exc:
                    logger.warning("GCS download failed for %s: %s", name, exc)
            if batch:
                yield batch
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        page_token = ""
        while True:
            data = await self._list_objects(page_token)
            items = data.get("items", [])
            if not items:
                break
            batch: list[SourceDocument] = []
            for obj in items:
                updated = obj.get("updated", "")
                if updated:
                    from dateutil.parser import isoparse
                    dt = isoparse(updated)
                    if dt < start or dt >= end:
                        continue
                if not self._should_include(obj.get("name", "")):
                    continue
                try:
                    content = await self._download_object(obj["name"])
                    batch.append(self._obj_to_doc(obj, content))
                except Exception:
                    pass
            if batch:
                yield batch
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
        # Checkpoint managed by SyncEngine

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        params: dict[str, Any] = {
            "prefix": path or self._prefix,
            "delimiter": "/",
            "maxResults": page_size,
        }
        if cursor:
            params["pageToken"] = cursor
        r = await self._client.get(f"{GCS_API}/b/{self._bucket}/o", params=params)
        r.raise_for_status()
        data = r.json()

        items: list[ContentItem] = []
        for prefix in data.get("prefixes", []):
            items.append(ContentItem(
                id=prefix, name=prefix.rstrip("/").split("/")[-1],
                path=prefix, item_type="folder",
            ))
        for obj in data.get("items", []):
            name = obj.get("name", "")
            if name == (path or self._prefix):
                continue
            items.append(ContentItem(
                id=name, name=name.split("/")[-1],
                path=name, item_type="file",
                size_bytes=int(obj.get("size", 0)),
                updated_at=obj.get("updated"),
            ))
        return ContentListResponse(
            items=items,
            cursor=data.get("nextPageToken"),
            has_more=bool(data.get("nextPageToken")),
        )
