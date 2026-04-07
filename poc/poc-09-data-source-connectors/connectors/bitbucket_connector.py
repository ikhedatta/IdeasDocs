"""Bitbucket connector — ingest repository files and pull requests from Bitbucket Cloud."""

from __future__ import annotations

import base64
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

BB_API = "https://api.bitbucket.org/2.0"


@register(SourceType.BITBUCKET)
class BitbucketConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest from Bitbucket Cloud via REST API 2.0."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.BITBUCKET,
            display_name="Bitbucket",
            description="Sync repository files, pull requests, and issues from Bitbucket Cloud.",
            icon="git-branch",
            category="dev_tools",
            auth_methods=[AuthMethod.APP_PASSWORD, AuthMethod.OAUTH2],
            default_auth=AuthMethod.APP_PASSWORD,
            config_schema={
                "workspace": {"type": "string", "required": True, "description": "Bitbucket workspace slug"},
                "repos": {"type": "array", "items": "string", "description": "Repo slugs (empty = all in workspace)"},
                "include_prs": {"type": "boolean", "default": True},
                "include_repo_files": {"type": "boolean", "default": True},
                "branch": {"type": "string", "default": "main"},
                "file_extensions": {"type": "array", "items": "string",
                                    "default": ["md", "txt", "rst"]},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._workspace = cfg["workspace"]
        self._repos: list[str] = cfg.get("repos", [])
        self._branch = cfg.get("branch", "main")
        self._include_prs = cfg.get("include_prs", True)
        self._include_files = cfg.get("include_repo_files", True)
        self._extensions = set(cfg.get("file_extensions", ["md", "txt", "rst"]))

        auth = (creds["username"], creds["app_password"])
        self._client = httpx.AsyncClient(
            base_url=BB_API,
            auth=auth,
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/user")
            return r.status_code == 200
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    async def _list_repos(self) -> list[dict]:
        if self._repos:
            repos = []
            for slug in self._repos:
                r = await self._client.get(f"/repositories/{self._workspace}/{slug}")
                r.raise_for_status()
                repos.append(r.json())
            return repos
        r = await self._client.get(f"/repositories/{self._workspace}", params={"pagelen": 100})
        r.raise_for_status()
        return r.json().get("values", [])

    async def _get_src_tree(self, repo_slug: str, path: str = "") -> list[dict]:
        items: list[dict] = []
        url = f"/repositories/{self._workspace}/{repo_slug}/src/{self._branch}/{path}"
        while url:
            r = await self._client.get(url, params={"pagelen": 100})
            r.raise_for_status()
            data = r.json()
            items.extend(data.get("values", []))
            url = data.get("next", "")
        return items

    async def _get_file(self, repo_slug: str, path: str) -> bytes:
        r = await self._client.get(
            f"/repositories/{self._workspace}/{repo_slug}/src/{self._branch}/{path}"
        )
        r.raise_for_status()
        return r.content

    async def _get_prs(self, repo_slug: str, updated_on_after: str = "", page: int = 1) -> dict:
        params: dict[str, Any] = {"pagelen": 50, "page": page, "state": "MERGED,OPEN"}
        if updated_on_after:
            params["q"] = f'updated_on > {updated_on_after}'
        r = await self._client.get(
            f"/repositories/{self._workspace}/{repo_slug}/pullrequests", params=params
        )
        r.raise_for_status()
        return r.json()

    def _file_to_doc(self, repo_slug: str, entry: dict, content: bytes) -> SourceDocument:
        path = entry.get("path", "")
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        return SourceDocument(
            source_id=f"bitbucket:{self._workspace}/{repo_slug}:{path}",
            source_type=SourceType.BITBUCKET,
            connector_id=self.config.id,
            title=path,
            content=content,
            extension=ext,
            url=entry.get("links", {}).get("html", {}).get("href", ""),
            metadata={"workspace": self._workspace, "repo": repo_slug, "branch": self._branch},
        )

    def _pr_to_doc(self, repo_slug: str, pr: dict) -> SourceDocument:
        title = pr.get("title", "")
        desc = pr.get("description", "") or ""
        text = f"# PR #{pr['id']}: {title}\n\n{desc}"
        return SourceDocument(
            source_id=f"bitbucket:{self._workspace}/{repo_slug}:pr:{pr['id']}",
            source_type=SourceType.BITBUCKET,
            connector_id=self.config.id,
            title=f"PR #{pr['id']}: {title}",
            content=text.encode("utf-8"),
            mime_type="text/markdown",
            extension="md",
            url=pr.get("links", {}).get("html", {}).get("href", ""),
            updated_at=pr.get("updated_on"),
            metadata={"workspace": self._workspace, "repo": repo_slug, "state": pr.get("state")},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        repos = await self._list_repos()
        for repo in repos:
            slug = repo["slug"]

            if self._include_files:
                entries = await self._get_src_tree(slug)
                batch: list[SourceDocument] = []
                for e in entries:
                    if e.get("type") != "commit_file":
                        continue
                    ext = e["path"].rsplit(".", 1)[-1] if "." in e["path"] else ""
                    if self._extensions and ext not in self._extensions:
                        continue
                    try:
                        content = await self._get_file(slug, e["path"])
                        batch.append(self._file_to_doc(slug, e, content))
                    except Exception as exc:
                        logger.warning("Bitbucket file fetch failed: %s", exc)
                    if len(batch) >= 50:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            if self._include_prs:
                page = 1
                while True:
                    data = await self._get_prs(slug, page=page)
                    prs = data.get("values", [])
                    if not prs:
                        break
                    yield [self._pr_to_doc(slug, pr) for pr in prs]
                    if not data.get("next"):
                        break
                    page += 1

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        repos = await self._list_repos()
        for repo in repos:
            slug = repo["slug"]
            if self._include_prs:
                page = 1
                while True:
                    data = await self._get_prs(slug, updated_on_after=start.isoformat(), page=page)
                    prs = data.get("values", [])
                    if not prs:
                        break
                    filtered = [p for p in prs if p.get("updated_on", "") < end.isoformat()]
                    if filtered:
                        yield [self._pr_to_doc(slug, pr) for pr in filtered]
                    if not data.get("next"):
                        break
                    page += 1
        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            repos = await self._list_repos()
            items = [
                ContentItem(
                    id=r["slug"], name=r.get("full_name", r["slug"]),
                    path=r["slug"], item_type="repo",
                    metadata={"description": r.get("description", ""), "is_private": r.get("is_private")},
                )
                for r in repos[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(repos) > page_size)
        else:
            entries = await self._get_src_tree(path)
            items = [
                ContentItem(
                    id=e.get("path", ""), name=e.get("path", "").split("/")[-1],
                    path=e.get("path", ""),
                    item_type="folder" if e.get("type") == "commit_directory" else "file",
                    size_bytes=e.get("size"),
                )
                for e in entries[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(entries) > page_size)
