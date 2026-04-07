"""Jira connector — ingest issues and attachments from Atlassian Jira Cloud."""

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


@register(SourceType.JIRA)
class JiraConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest issues from Jira Cloud via REST API v3."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.JIRA,
            display_name="Jira",
            description="Sync issues, comments, and attachments from Atlassian Jira Cloud.",
            icon="check-square",
            category="project_management",
            auth_methods=[AuthMethod.API_KEY, AuthMethod.OAUTH2],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "cloud_url": {"type": "string", "required": True, "description": "e.g. https://yoursite.atlassian.net"},
                "project_keys": {"type": "array", "items": "string", "description": "Projects to sync (empty = all)"},
                "jql_filter": {"type": "string", "description": "Custom JQL filter", "default": ""},
                "include_comments": {"type": "boolean", "default": True},
                "include_attachments": {"type": "boolean", "default": False},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._base = cfg["cloud_url"].rstrip("/")
        self._project_keys: list[str] = cfg.get("project_keys", [])
        self._jql_filter = cfg.get("jql_filter", "")
        self._include_comments = cfg.get("include_comments", True)

        self._client = httpx.AsyncClient(
            base_url=f"{self._base}/rest/api/3",
            auth=(creds["email"], creds["api_token"]),
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/myself")
            return r.status_code == 200
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    def _build_jql(self, extra: str = "") -> str:
        parts = []
        if self._project_keys:
            keys = ", ".join(f'"{k}"' for k in self._project_keys)
            parts.append(f"project in ({keys})")
        if self._jql_filter:
            parts.append(f"({self._jql_filter})")
        if extra:
            parts.append(extra)
        return " AND ".join(parts) if parts else "ORDER BY updated DESC"

    async def _search_issues(self, jql: str, start_at: int = 0) -> dict:
        r = await self._client.post("/search", json={
            "jql": jql,
            "startAt": start_at,
            "maxResults": 50,
            "fields": ["summary", "description", "status", "assignee", "reporter",
                       "created", "updated", "project", "issuetype", "comment"],
        })
        r.raise_for_status()
        return r.json()

    def _issue_to_doc(self, issue: dict) -> SourceDocument:
        fields = issue.get("fields", {})
        desc = ""
        if fields.get("description"):
            # ADF → plain text (simplified)
            desc = self._adf_to_text(fields["description"])

        comments_text = ""
        if self._include_comments and fields.get("comment", {}).get("comments"):
            for c in fields["comment"]["comments"]:
                author = c.get("author", {}).get("displayName", "unknown")
                body = self._adf_to_text(c.get("body", {}))
                comments_text += f"\n---\nComment by {author}:\n{body}\n"

        text = f"[{issue['key']}] {fields.get('summary', '')}\n\n{desc}{comments_text}"

        return SourceDocument(
            source_id=issue["key"],
            source_type=SourceType.JIRA,
            connector_id=self.config.id,
            title=f"{issue['key']}: {fields.get('summary', '')}",
            content=text.encode("utf-8"),
            mime_type="text/plain",
            extension="txt",
            url=f"{self._base}/browse/{issue['key']}",
            updated_at=fields.get("updated"),
            metadata={
                "project": fields.get("project", {}).get("key", ""),
                "status": fields.get("status", {}).get("name", ""),
                "type": fields.get("issuetype", {}).get("name", ""),
                "assignee": (fields.get("assignee") or {}).get("displayName", ""),
            },
        )

    @staticmethod
    def _adf_to_text(adf: dict | str) -> str:
        """Minimal ADF (Atlassian Document Format) → plain text."""
        if isinstance(adf, str):
            return adf
        if not isinstance(adf, dict):
            return ""
        texts: list[str] = []
        for node in adf.get("content", []):
            if node.get("type") == "paragraph":
                for inline in node.get("content", []):
                    if inline.get("type") == "text":
                        texts.append(inline.get("text", ""))
                texts.append("\n")
            elif node.get("type") == "heading":
                for inline in node.get("content", []):
                    if inline.get("type") == "text":
                        texts.append(inline.get("text", ""))
                texts.append("\n")
        return "".join(texts).strip()

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        jql = self._build_jql()
        start_at = 0
        while True:
            data = await self._search_issues(jql, start_at)
            issues = data.get("issues", [])
            if not issues:
                break
            yield [self._issue_to_doc(i) for i in issues]
            start_at += len(issues)
            if start_at >= data.get("total", 0):
                break

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        fmt = "%Y-%m-%d %H:%M"
        extra = f'updated >= "{start.strftime(fmt)}" AND updated < "{end.strftime(fmt)}"'
        jql = self._build_jql(extra)
        start_at = 0

        while True:
            data = await self._search_issues(jql, start_at)
            issues = data.get("issues", [])
            if not issues:
                break
            yield [self._issue_to_doc(i) for i in issues]
            start_at += len(issues)
            if start_at >= data.get("total", 0):
                break

        # Checkpoint managed by SyncEngine

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        r = await self._client.get("/project/search", params={"maxResults": page_size})
        r.raise_for_status()
        data = r.json()
        items = [
            ContentItem(
                id=p["key"], name=f"{p['key']} — {p.get('name', '')}",
                path=p["key"], item_type="project",
                metadata={"style": p.get("style", ""), "lead": p.get("lead", {}).get("displayName", "")},
            )
            for p in data.get("values", [])
        ]
        return ContentListResponse(items=items, has_more=data.get("isLast") is False)
