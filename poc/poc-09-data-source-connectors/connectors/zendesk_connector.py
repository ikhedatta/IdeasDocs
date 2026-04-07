"""Zendesk connector — ingest articles and tickets from Zendesk."""

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


@register(SourceType.ZENDESK)
class ZendeskConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest Help Center articles and tickets from Zendesk."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.ZENDESK,
            display_name="Zendesk",
            description="Sync Help Center articles and support tickets from Zendesk.",
            icon="headphones",
            category="collaboration",
            auth_methods=[AuthMethod.API_KEY, AuthMethod.BASIC],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "subdomain": {"type": "string", "required": True, "description": "yourcompany.zendesk.com"},
                "include_articles": {"type": "boolean", "default": True},
                "include_tickets": {"type": "boolean", "default": False},
                "category_ids": {"type": "array", "items": "string", "description": "Article category IDs (empty = all)"},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._subdomain = cfg["subdomain"]
        self._include_articles = cfg.get("include_articles", True)
        self._include_tickets = cfg.get("include_tickets", False)
        self._category_ids = cfg.get("category_ids", [])

        base = f"https://{self._subdomain}.zendesk.com"
        auth = (f"{creds['email']}/token", creds["api_token"])
        self._client = httpx.AsyncClient(base_url=base, auth=auth, timeout=60)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/api/v2/users/me")
            return r.status_code == 200
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_articles(self, page: int = 1) -> dict:
        r = await self._client.get(
            "/api/v2/help_center/articles",
            params={"per_page": 50, "page": page, "sort_by": "updated_at", "sort_order": "desc"},
        )
        r.raise_for_status()
        return r.json()

    async def _get_tickets(self, page: str = "", sort_by: str = "updated_at") -> dict:
        params: dict[str, Any] = {"per_page": 50, "sort_by": sort_by}
        url = page if page else "/api/v2/tickets"
        r = await self._client.get(url, params=params if not page else {})
        r.raise_for_status()
        return r.json()

    def _article_to_doc(self, article: dict) -> SourceDocument:
        title = article.get("title", "Untitled")
        body = article.get("body", "")
        return SourceDocument(
            source_id=f"zendesk:article:{article['id']}",
            source_type=SourceType.ZENDESK,
            connector_id=self.config.id,
            title=title,
            content=body.encode("utf-8"),
            mime_type="text/html",
            extension="html",
            url=article.get("html_url", ""),
            updated_at=article.get("updated_at"),
            metadata={
                "section_id": article.get("section_id"),
                "locale": article.get("locale"),
                "draft": article.get("draft", False),
                "label_names": article.get("label_names", []),
            },
        )

    def _ticket_to_doc(self, ticket: dict) -> SourceDocument:
        subject = ticket.get("subject", "(no subject)")
        desc = ticket.get("description", "")
        text = f"Subject: {subject}\nStatus: {ticket.get('status', '')}\n\n{desc}"
        return SourceDocument(
            source_id=f"zendesk:ticket:{ticket['id']}",
            source_type=SourceType.ZENDESK,
            connector_id=self.config.id,
            title=subject,
            content=text.encode("utf-8"),
            mime_type="text/plain",
            extension="txt",
            url=f"https://{self._subdomain}.zendesk.com/agent/tickets/{ticket['id']}",
            updated_at=ticket.get("updated_at"),
            metadata={
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "type": ticket.get("type"),
                "tags": ticket.get("tags", []),
            },
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        if self._include_articles:
            page = 1
            while True:
                data = await self._get_articles(page)
                articles = data.get("articles", [])
                if not articles:
                    break
                yield [self._article_to_doc(a) for a in articles]
                if not data.get("next_page"):
                    break
                page += 1

        if self._include_tickets:
            next_page = ""
            while True:
                data = await self._get_tickets(page=next_page)
                tickets = data.get("tickets", [])
                if not tickets:
                    break
                yield [self._ticket_to_doc(t) for t in tickets]
                next_page = data.get("next_page", "")
                if not next_page:
                    break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        if self._include_articles:
            page = 1
            while True:
                data = await self._get_articles(page)
                articles = data.get("articles", [])
                if not articles:
                    break
                filtered = [
                    a for a in articles
                    if a.get("updated_at", "") >= start.isoformat()
                    and a.get("updated_at", "") < end.isoformat()
                ]
                if filtered:
                    yield [self._article_to_doc(a) for a in filtered]
                # Stop if we've gone past the end window
                oldest = articles[-1].get("updated_at", "")
                if oldest and oldest < start.isoformat():
                    break
                if not data.get("next_page"):
                    break
                page += 1

        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            # List categories
            r = await self._client.get("/api/v2/help_center/categories", params={"per_page": page_size})
            r.raise_for_status()
            data = r.json()
            items = [
                ContentItem(
                    id=str(c["id"]), name=c.get("name", ""),
                    path=str(c["id"]), item_type="folder",
                    metadata={"description": c.get("description", "")},
                )
                for c in data.get("categories", [])
            ]
            return ContentListResponse(items=items, has_more=bool(data.get("next_page")))
        else:
            # List sections in category
            r = await self._client.get(
                f"/api/v2/help_center/categories/{path}/sections",
                params={"per_page": page_size},
            )
            r.raise_for_status()
            data = r.json()
            items = [
                ContentItem(
                    id=str(s["id"]), name=s.get("name", ""),
                    path=f"{path}/{s['id']}", item_type="folder",
                )
                for s in data.get("sections", [])
            ]
            return ContentListResponse(items=items, has_more=bool(data.get("next_page")))
