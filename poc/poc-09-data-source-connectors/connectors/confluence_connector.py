"""Confluence connector — ingest pages and attachments from Atlassian Confluence Cloud."""

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

_CQL_DATE_FMT = "%Y-%m-%d %H:%M"


@register(SourceType.CONFLUENCE)
class ConfluenceConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest pages and attachments from Confluence Cloud (REST API v2)."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.CONFLUENCE,
            display_name="Confluence",
            description="Sync pages, blog posts, and attachments from Atlassian Confluence Cloud.",
            icon="book-open",
            category="collaboration",
            auth_methods=[AuthMethod.API_KEY, AuthMethod.OAUTH2],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "cloud_url": {"type": "string", "required": True, "description": "e.g. https://yoursite.atlassian.net"},
                "space_keys": {"type": "array", "items": "string", "description": "Space keys to sync (empty = all)"},
                "include_attachments": {"type": "boolean", "default": True},
                "include_blogs": {"type": "boolean", "default": False},
                "max_attachment_mb": {"type": "number", "default": 50},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._base = cfg["cloud_url"].rstrip("/")
        self._include_attachments = cfg.get("include_attachments", True)
        self._include_blogs = cfg.get("include_blogs", False)
        self._space_keys: list[str] = cfg.get("space_keys", [])
        self._max_attach_bytes = cfg.get("max_attachment_mb", 50) * 1024 * 1024

        auth = (creds["email"], creds["api_token"])
        self._client = httpx.AsyncClient(
            base_url=f"{self._base}/wiki/api/v2",
            auth=auth,
            timeout=60,
        )
        logger.info("Confluence connected: %s", self._base)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/spaces", params={"limit": 1})
            return r.status_code == 200
        except Exception as exc:
            logger.error("Confluence validation failed: %s", exc)
            return False

    # ── Internal helpers ───────────────────────────────────────────

    async def _get_pages(self, cql_extra: str = "", cursor: str = "") -> dict:
        """CQL search with pagination."""
        import httpx

        cql = "type=page"
        if self._space_keys:
            spaces = " OR ".join(f'space="{s}"' for s in self._space_keys)
            cql += f" AND ({spaces})"
        if cql_extra:
            cql += f" AND {cql_extra}"

        params: dict[str, Any] = {"cql": cql, "limit": 50, "expand": "body.storage,version"}
        if cursor:
            params["cursor"] = cursor

        # v1 search endpoint (CQL works better here)
        r = await self._client.get(
            f"{self._base}/wiki/rest/api/content/search",
            params=params,
        )
        r.raise_for_status()
        return r.json()

    def _page_to_doc(self, page: dict) -> SourceDocument:
        body_html = page.get("body", {}).get("storage", {}).get("value", "")
        return SourceDocument(
            source_id=page["id"],
            source_type=SourceType.CONFLUENCE,
            connector_id=self.config.id,
            title=page.get("title", "Untitled"),
            content=body_html.encode("utf-8"),
            mime_type="text/html",
            extension="html",
            url=f"{self._base}/wiki{page.get('_links', {}).get('webui', '')}",
            updated_at=page.get("version", {}).get("when"),
            metadata={
                "space_key": page.get("space", {}).get("key", ""),
                "version": page.get("version", {}).get("number"),
                "status": page.get("status"),
            },
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        cursor = ""
        while True:
            data = await self._get_pages(cursor=cursor)
            results = data.get("results", [])
            if not results:
                break
            yield [self._page_to_doc(p) for p in results]
            links = data.get("_links", {})
            if "next" not in links:
                break
            # Extract cursor from next URL
            import urllib.parse
            parts = urllib.parse.urlparse(links["next"])
            qs = urllib.parse.parse_qs(parts.query)
            cursor = qs.get("cursor", [""])[0]
            if not cursor:
                break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        cql_extra = f'lastModified >= "{start.strftime(_CQL_DATE_FMT)}" AND lastModified < "{end.strftime(_CQL_DATE_FMT)}"'
        cursor = ""
        while True:
            data = await self._get_pages(cql_extra=cql_extra, cursor=cursor)
            results = data.get("results", [])
            if not results:
                break
            yield [self._page_to_doc(p) for p in results]
            links = data.get("_links", {})
            if "next" not in links:
                break
            import urllib.parse
            parts = urllib.parse.urlparse(links["next"])
            qs = urllib.parse.parse_qs(parts.query)
            cursor = qs.get("cursor", [""])[0]
            if not cursor:
                break

        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            # List spaces
            r = await self._client.get("/spaces", params={"limit": page_size})
            r.raise_for_status()
            data = r.json()
            items = [
                ContentItem(
                    id=s["key"], name=s.get("name", s["key"]),
                    path=s["key"], item_type="space",
                    metadata={"description": s.get("description", {}).get("plain", {}).get("value", "")},
                )
                for s in data.get("results", [])
            ]
            return ContentListResponse(items=items, has_more=bool(data.get("_links", {}).get("next")))
        else:
            # List pages in space
            params: dict[str, Any] = {"limit": page_size, "status": "current"}
            r = await self._client.get(f"/spaces/{path}/pages", params=params)
            r.raise_for_status()
            data = r.json()
            items = [
                ContentItem(
                    id=p["id"], name=p.get("title", "Untitled"),
                    path=f"{path}/{p['id']}", item_type="page",
                    updated_at=p.get("version", {}).get("when"),
                )
                for p in data.get("results", [])
            ]
            return ContentListResponse(items=items, has_more=bool(data.get("_links", {}).get("next")))
