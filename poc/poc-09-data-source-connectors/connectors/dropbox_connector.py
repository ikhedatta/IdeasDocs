"""Dropbox connector — ingest files from Dropbox."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Generator, Optional

from interfaces import BaseConnector, BrowsableConnector, LoadConnector, OAuthConnector, PollConnector
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

DROPBOX_API = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT = "https://content.dropboxapi.com/2"


@register(SourceType.DROPBOX)
class DropboxConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector, OAuthConnector):
    """Ingest files from Dropbox via HTTP API v2."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.DROPBOX,
            display_name="Dropbox",
            description="Sync files and folders from Dropbox.",
            icon="inbox",
            category="cloud_storage",
            auth_methods=[AuthMethod.OAUTH2, AuthMethod.API_KEY],
            default_auth=AuthMethod.OAUTH2,
            config_schema={
                "root_path": {"type": "string", "default": "", "description": "Folder path (empty = entire Dropbox)"},
                "file_extensions": {"type": "array", "items": "string"},
                "max_file_mb": {"type": "number", "default": 100},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._root = cfg.get("root_path", "")
        self._extensions = set(cfg.get("file_extensions", []))
        self._max_bytes = cfg.get("max_file_mb", 100) * 1024 * 1024
        token = creds.get("access_token") or creds.get("api_key", "")

        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.post(f"{DROPBOX_API}/users/get_current_account")
            return r.status_code == 200
        except Exception:
            return False

    # ── OAuth ──────────────────────────────────────────────────────

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        from config import DROPBOX_APP_KEY
        from urllib.parse import urlencode

        params = {
            "client_id": DROPBOX_APP_KEY,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "token_access_type": "offline",
            "state": state,
        }
        return f"https://www.dropbox.com/oauth2/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        import httpx
        from config import DROPBOX_APP_KEY, DROPBOX_APP_SECRET

        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.dropboxapi.com/oauth2/token", data={
                "code": code, "grant_type": "authorization_code",
                "client_id": DROPBOX_APP_KEY, "client_secret": DROPBOX_APP_SECRET,
                "redirect_uri": redirect_uri,
            })
            r.raise_for_status()
            return r.json()

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        import httpx
        from config import DROPBOX_APP_KEY, DROPBOX_APP_SECRET

        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.dropboxapi.com/oauth2/token", data={
                "refresh_token": refresh_token, "grant_type": "refresh_token",
                "client_id": DROPBOX_APP_KEY, "client_secret": DROPBOX_APP_SECRET,
            })
            r.raise_for_status()
            return r.json()

    # ── Helpers ─────────────────────────────────────────────────────

    def _should_include(self, name: str) -> bool:
        if not self._extensions:
            return True
        return any(name.lower().endswith(f".{ext}") for ext in self._extensions)

    async def _list_folder(self, path: str, cursor: str = "") -> dict:
        if cursor:
            r = await self._client.post(
                f"{DROPBOX_API}/files/list_folder/continue",
                json={"cursor": cursor},
            )
        else:
            r = await self._client.post(
                f"{DROPBOX_API}/files/list_folder",
                json={"path": path or "", "recursive": True, "limit": 500},
            )
        r.raise_for_status()
        return r.json()

    async def _download(self, path: str) -> bytes:
        import json as _json

        r = await self._client.post(
            f"{DROPBOX_CONTENT}/files/download",
            headers={
                "Dropbox-API-Arg": _json.dumps({"path": path}),
                "Content-Type": "application/octet-stream",
            },
            content=b"",
        )
        r.raise_for_status()
        return r.content

    def _entry_to_doc(self, entry: dict, content: bytes) -> SourceDocument:
        name = entry.get("name", "")
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        return SourceDocument(
            source_id=entry["id"],
            source_type=SourceType.DROPBOX,
            connector_id=self.config.id,
            title=name,
            content=content,
            extension=ext,
            size_bytes=entry.get("size", len(content)),
            url=f"dropbox://{entry.get('path_display', '')}",
            updated_at=entry.get("server_modified"),
            metadata={"path": entry.get("path_display", ""), "rev": entry.get("rev", "")},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        cursor = ""
        while True:
            data = await self._list_folder(self._root, cursor)
            entries = [e for e in data.get("entries", []) if e[".tag"] == "file"]
            batch: list[SourceDocument] = []
            for e in entries:
                if not self._should_include(e.get("name", "")):
                    continue
                if e.get("size", 0) > self._max_bytes:
                    continue
                try:
                    content = await self._download(e["path_lower"])
                    batch.append(self._entry_to_doc(e, content))
                except Exception as exc:
                    logger.warning("Failed to download %s: %s", e.get("path_display"), exc)
            if batch:
                yield batch
            if not data.get("has_more"):
                break
            cursor = data.get("cursor", "")

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        # Use saved cursor for incremental listing if available
        saved_cursor = checkpoint.cursor if checkpoint else ""
        if saved_cursor:
            data = await self._list_folder("", cursor=saved_cursor)
        else:
            data = await self._list_folder(self._root)

        new_cursor = data.get("cursor", "")
        entries = [e for e in data.get("entries", []) if e[".tag"] == "file"]
        # Filter by modification time
        batch: list[SourceDocument] = []
        for e in entries:
            mod = e.get("server_modified", "")
            if mod:
                mod_dt = datetime.fromisoformat(mod.replace("Z", "+00:00"))
                if mod_dt < start or mod_dt >= end:
                    continue
            if not self._should_include(e.get("name", "")):
                continue
            try:
                content = await self._download(e["path_lower"])
                batch.append(self._entry_to_doc(e, content))
            except Exception:
                pass
        if batch:
            yield batch

        # Checkpoint managed by SyncEngine

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        # Non-recursive listing for browsing
        r = await self._client.post(
            f"{DROPBOX_API}/files/list_folder",
            json={"path": path or "", "recursive": False, "limit": page_size},
        )
        r.raise_for_status()
        data = r.json()
        items: list[ContentItem] = []
        for e in data.get("entries", []):
            is_folder = e[".tag"] == "folder"
            items.append(ContentItem(
                id=e["id"], name=e.get("name", ""),
                path=e.get("path_display", ""),
                item_type="folder" if is_folder else "file",
                size_bytes=e.get("size") if not is_folder else None,
                updated_at=e.get("server_modified") if not is_folder else None,
            ))
        return ContentListResponse(
            items=items,
            cursor=data.get("cursor") if data.get("has_more") else None,
            has_more=data.get("has_more", False),
        )
