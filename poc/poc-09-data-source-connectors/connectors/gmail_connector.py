"""Gmail connector — ingest emails and attachments from Gmail."""

from __future__ import annotations

import base64
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

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@register(SourceType.GMAIL)
class GmailConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector, OAuthConnector):
    """Ingest emails from Gmail via Gmail API v1."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.GMAIL,
            display_name="Gmail",
            description="Sync emails and attachments from Gmail accounts.",
            icon="mail",
            category="communication",
            auth_methods=[AuthMethod.OAUTH2],
            default_auth=AuthMethod.OAUTH2,
            config_schema={
                "label_ids": {"type": "array", "items": "string", "description": "Label IDs to sync (empty = INBOX)"},
                "query": {"type": "string", "description": "Gmail search query filter", "default": ""},
                "include_attachments": {"type": "boolean", "default": True},
                "max_results": {"type": "integer", "default": 5000},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._label_ids: list[str] = cfg.get("label_ids", ["INBOX"])
        self._query = cfg.get("query", "")
        self._include_attachments = cfg.get("include_attachments", True)
        self._max_results = cfg.get("max_results", 5000)

        self._client = httpx.AsyncClient(
            base_url="https://gmail.googleapis.com/gmail/v1/users/me",
            headers={"Authorization": f"Bearer {creds['access_token']}"},
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/profile")
            return r.status_code == 200
        except Exception:
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
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
            })
            r.raise_for_status()
            return r.json()

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        import httpx
        from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

        async with httpx.AsyncClient() as client:
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "refresh_token": refresh_token, "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET, "grant_type": "refresh_token",
            })
            r.raise_for_status()
            return r.json()

    # ── Helpers ─────────────────────────────────────────────────────

    async def _list_messages(self, query: str = "", page_token: str = "") -> dict:
        params: dict[str, Any] = {"maxResults": 100}
        if self._label_ids:
            params["labelIds"] = ",".join(self._label_ids)
        q = self._query
        if query:
            q = f"{q} {query}".strip() if q else query
        if q:
            params["q"] = q
        if page_token:
            params["pageToken"] = page_token
        r = await self._client.get("/messages", params=params)
        r.raise_for_status()
        return r.json()

    async def _get_message(self, msg_id: str) -> dict:
        r = await self._client.get(f"/messages/{msg_id}", params={"format": "full"})
        r.raise_for_status()
        return r.json()

    def _extract_body(self, payload: dict) -> str:
        """Recursively extract text/plain body from MIME parts."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            text = self._extract_body(part)
            if text:
                return text
        return ""

    def _msg_to_doc(self, msg: dict) -> SourceDocument:
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        sender = headers.get("from", "unknown")
        date_str = headers.get("date", "")
        body = self._extract_body(msg.get("payload", {}))
        text = f"From: {sender}\nSubject: {subject}\nDate: {date_str}\n\n{body}"

        return SourceDocument(
            source_id=msg["id"],
            source_type=SourceType.GMAIL,
            connector_id=self.config.id,
            title=subject,
            content=text.encode("utf-8"),
            mime_type="text/plain",
            extension="txt",
            metadata={"from": sender, "subject": subject, "labels": msg.get("labelIds", [])},
            size_bytes=int(msg.get("sizeEstimate", len(text))),
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        page_token = ""
        total = 0
        while total < self._max_results:
            data = await self._list_messages(page_token=page_token)
            msg_refs = data.get("messages", [])
            if not msg_refs:
                break
            batch: list[SourceDocument] = []
            for ref in msg_refs:
                try:
                    msg = await self._get_message(ref["id"])
                    batch.append(self._msg_to_doc(msg))
                except Exception as exc:
                    logger.warning("Failed to fetch message %s: %s", ref["id"], exc)
            if batch:
                yield batch
            total += len(msg_refs)
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        epoch_start = int(start.timestamp())
        epoch_end = int(end.timestamp())
        query = f"after:{epoch_start} before:{epoch_end}"
        page_token = ""

        while True:
            data = await self._list_messages(query=query, page_token=page_token)
            msg_refs = data.get("messages", [])
            if not msg_refs:
                break
            batch = []
            for ref in msg_refs:
                try:
                    msg = await self._get_message(ref["id"])
                    batch.append(self._msg_to_doc(msg))
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
        r = await self._client.get("/labels")
        r.raise_for_status()
        labels = r.json().get("labels", [])
        items = [
            ContentItem(
                id=lbl["id"], name=lbl.get("name", lbl["id"]),
                path=lbl["id"], item_type="folder",
                metadata={"type": lbl.get("type", "user")},
            )
            for lbl in labels
            if lbl.get("type") != "system" or lbl["id"] in ("INBOX", "SENT", "IMPORTANT", "STARRED")
        ]
        return ContentListResponse(items=items, has_more=False)
