"""Google Drive connector — ingest files from Google Drive."""

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

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MIME_EXPORT_MAP = {
    "application/vnd.google-apps.document": ("text/html", "html"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", "pdf"),
}


@register(SourceType.GOOGLE_DRIVE)
class GoogleDriveConnector(
    BaseConnector, LoadConnector, PollConnector, BrowsableConnector, OAuthConnector
):
    """Ingest files from Google Drive via Drive API v3."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.GOOGLE_DRIVE,
            display_name="Google Drive",
            description="Sync documents, spreadsheets, and files from Google Drive.",
            icon="hard-drive",
            category="cloud_storage",
            auth_methods=[AuthMethod.OAUTH2, AuthMethod.SERVICE_ACCOUNT],
            default_auth=AuthMethod.OAUTH2,
            config_schema={
                "folder_ids": {"type": "array", "items": "string", "description": "Folder IDs to sync (empty = entire drive)"},
                "shared_drives": {"type": "array", "items": "string", "description": "Shared/team drive IDs"},
                "file_extensions": {"type": "array", "items": "string", "description": "Filter by extension"},
                "max_file_mb": {"type": "number", "default": 100},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._folder_ids: list[str] = cfg.get("folder_ids", [])
        self._max_bytes = cfg.get("max_file_mb", 100) * 1024 * 1024

        self._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/drive/v3",
            headers={"Authorization": f"Bearer {creds['access_token']}"},
            timeout=60,
        )
        logger.info("Google Drive connected")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/about", params={"fields": "user"})
            return r.status_code == 200
        except Exception as exc:
            logger.error("Google Drive validation failed: %s", exc)
            return False

    # ── OAuth ──────────────────────────────────────────────────────

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        from config import GOOGLE_CLIENT_ID
        from urllib.parse import urlencode

        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "state": state,
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        import httpx
        from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            r.raise_for_status()
            return r.json()

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        import httpx
        from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "refresh_token": refresh_token,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            return r.json()

    # ── Helpers ─────────────────────────────────────────────────────

    async def _list_files(self, query: str = "", page_token: str = "") -> dict:
        params: dict[str, Any] = {
            "pageSize": 100,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents)",
        }
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        r = await self._client.get("/files", params=params)
        r.raise_for_status()
        return r.json()

    async def _download_file(self, file_id: str, mime_type: str) -> tuple[bytes, str, str]:
        if mime_type in MIME_EXPORT_MAP:
            export_mime, ext = MIME_EXPORT_MAP[mime_type]
            r = await self._client.get(f"/files/{file_id}/export", params={"mimeType": export_mime})
        else:
            r = await self._client.get(f"/files/{file_id}", params={"alt": "media"})
            export_mime = mime_type
            ext = ""
        r.raise_for_status()
        return r.content, export_mime, ext

    def _file_to_doc(self, f: dict, content: bytes, mime: str, ext: str) -> SourceDocument:
        fname = f.get("name", "untitled")
        if not ext:
            ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
        return SourceDocument(
            source_id=f["id"],
            source_type=SourceType.GOOGLE_DRIVE,
            connector_id=self.config.id,
            title=fname,
            content=content,
            mime_type=mime,
            extension=ext,
            size_bytes=int(f.get("size", len(content))),
            url=f.get("webViewLink", ""),
            updated_at=f.get("modifiedTime"),
            metadata={"parents": f.get("parents", [])},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        query_parts = ["trashed=false"]
        if self._folder_ids:
            folder_q = " or ".join(f"'{fid}' in parents" for fid in self._folder_ids)
            query_parts.append(f"({folder_q})")
        q = " and ".join(query_parts)
        page_token = ""

        while True:
            data = await self._list_files(query=q, page_token=page_token)
            files = data.get("files", [])
            if not files:
                break
            batch: list[SourceDocument] = []
            for f in files:
                size = int(f.get("size", 0))
                if size > self._max_bytes:
                    continue
                try:
                    content, mime, ext = await self._download_file(f["id"], f["mimeType"])
                    batch.append(self._file_to_doc(f, content, mime, ext))
                except Exception as exc:
                    logger.warning("Failed to download %s: %s", f["id"], exc)
            if batch:
                yield batch
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        q = f"trashed=false and modifiedTime >= '{start.isoformat()}Z' and modifiedTime < '{end.isoformat()}Z'"
        page_token = ""

        while True:
            data = await self._list_files(query=q, page_token=page_token)
            files = data.get("files", [])
            if not files:
                break
            batch: list[SourceDocument] = []
            for f in files:
                try:
                    content, mime, ext = await self._download_file(f["id"], f["mimeType"])
                    batch.append(self._file_to_doc(f, content, mime, ext))
                except Exception:
                    pass
            if batch:
                yield batch
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        q = "trashed=false"
        if path:
            q += f" and '{path}' in parents"
        else:
            q += " and 'root' in parents"

        data = await self._list_files(query=q, page_token=cursor or "")
        items: list[ContentItem] = []
        for f in data.get("files", []):
            is_folder = f["mimeType"] == "application/vnd.google-apps.folder"
            items.append(ContentItem(
                id=f["id"],
                name=f.get("name", ""),
                path=f["id"],
                item_type="folder" if is_folder else "file",
                size_bytes=int(f.get("size", 0)) if not is_folder else None,
                updated_at=f.get("modifiedTime"),
            ))
        return ContentListResponse(
            items=items,
            cursor=data.get("nextPageToken"),
            has_more=bool(data.get("nextPageToken")),
        )
