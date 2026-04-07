"""GitHub connector — ingest repository files, issues, and discussions."""

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

GITHUB_API = "https://api.github.com"


@register(SourceType.GITHUB)
class GitHubConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest from GitHub repositories via REST API."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.GITHUB,
            display_name="GitHub",
            description="Sync repository files, issues, pull requests, and discussions from GitHub.",
            icon="github",
            category="dev_tools",
            auth_methods=[AuthMethod.API_KEY, AuthMethod.OAUTH2],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "repos": {"type": "array", "items": "string", "required": True,
                          "description": "Repositories as owner/repo"},
                "include_issues": {"type": "boolean", "default": True},
                "include_prs": {"type": "boolean", "default": False},
                "include_repo_files": {"type": "boolean", "default": True},
                "branch": {"type": "string", "default": "main"},
                "file_extensions": {"type": "array", "items": "string",
                                    "default": ["md", "txt", "rst", "py", "js", "ts"]},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        token = creds.get("api_token") or creds.get("access_token", "")
        self._repos: list[str] = cfg.get("repos", [])
        self._branch = cfg.get("branch", "main")
        self._include_issues = cfg.get("include_issues", True)
        self._include_prs = cfg.get("include_prs", False)
        self._include_files = cfg.get("include_repo_files", True)
        self._extensions = set(cfg.get("file_extensions", ["md", "txt", "rst"]))

        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
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

    async def _get_tree(self, repo: str) -> list[dict]:
        r = await self._client.get(
            f"/repos/{repo}/git/trees/{self._branch}",
            params={"recursive": "1"},
        )
        r.raise_for_status()
        return r.json().get("tree", [])

    async def _get_file(self, repo: str, path: str) -> bytes:
        r = await self._client.get(f"/repos/{repo}/contents/{path}", params={"ref": self._branch})
        r.raise_for_status()
        data = r.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"])
        return (data.get("content", "") or "").encode()

    async def _get_issues(self, repo: str, since: str = "", page: int = 1, state: str = "all") -> list[dict]:
        params: dict[str, Any] = {"per_page": 50, "page": page, "state": state}
        if since:
            params["since"] = since
        r = await self._client.get(f"/repos/{repo}/issues", params=params)
        r.raise_for_status()
        return r.json()

    def _file_to_doc(self, repo: str, entry: dict, content: bytes) -> SourceDocument:
        path = entry["path"]
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        return SourceDocument(
            source_id=f"github:{repo}:{path}",
            source_type=SourceType.GITHUB,
            connector_id=self.config.id,
            title=path,
            content=content,
            extension=ext,
            size_bytes=entry.get("size", len(content)),
            url=f"https://github.com/{repo}/blob/{self._branch}/{path}",
            metadata={"repo": repo, "branch": self._branch, "sha": entry.get("sha", "")},
        )

    def _issue_to_doc(self, repo: str, issue: dict) -> SourceDocument:
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        labels = [l["name"] for l in issue.get("labels", [])]
        kind = "PR" if issue.get("pull_request") else "Issue"
        text = f"# [{kind}] {title}\n\nLabels: {', '.join(labels)}\n\n{body}"

        return SourceDocument(
            source_id=f"github:{repo}:issue:{issue['number']}",
            source_type=SourceType.GITHUB,
            connector_id=self.config.id,
            title=f"{kind} #{issue['number']}: {title}",
            content=text.encode("utf-8"),
            mime_type="text/markdown",
            extension="md",
            url=issue.get("html_url", ""),
            updated_at=issue.get("updated_at"),
            metadata={"repo": repo, "state": issue.get("state"), "labels": labels, "kind": kind},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        for repo in self._repos:
            if self._include_files:
                tree = await self._get_tree(repo)
                batch: list[SourceDocument] = []
                for entry in tree:
                    if entry["type"] != "blob":
                        continue
                    ext = entry["path"].rsplit(".", 1)[-1] if "." in entry["path"] else ""
                    if self._extensions and ext not in self._extensions:
                        continue
                    try:
                        content = await self._get_file(repo, entry["path"])
                        batch.append(self._file_to_doc(repo, entry, content))
                    except Exception as exc:
                        logger.warning("GitHub file fetch failed: %s — %s", entry["path"], exc)
                    if len(batch) >= 50:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            if self._include_issues:
                page = 1
                while True:
                    items = await self._get_issues(repo, page=page)
                    if not items:
                        break
                    # Separate issues from PRs
                    issues = [i for i in items if not i.get("pull_request")]
                    prs = [i for i in items if i.get("pull_request")] if self._include_prs else []
                    docs = [self._issue_to_doc(repo, i) for i in issues + prs]
                    if docs:
                        yield docs
                    page += 1

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        for repo in self._repos:
            if self._include_issues:
                page = 1
                while True:
                    items = await self._get_issues(repo, since=start.isoformat() + "Z", page=page)
                    if not items:
                        break
                    filtered = [i for i in items if i.get("updated_at", "") < end.isoformat() + "Z"]
                    issues = [i for i in filtered if not i.get("pull_request")]
                    prs = [i for i in filtered if i.get("pull_request")] if self._include_prs else []
                    docs = [self._issue_to_doc(repo, i) for i in issues + prs]
                    if docs:
                        yield docs
                    page += 1
        # Checkpoint managed by SyncEngine

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            # List user or org repos
            r = await self._client.get("/user/repos", params={"per_page": page_size, "sort": "updated"})
            r.raise_for_status()
            repos = r.json()
            items = [
                ContentItem(
                    id=rp["full_name"], name=rp["full_name"],
                    path=rp["full_name"], item_type="repo",
                    metadata={
                        "description": rp.get("description", ""),
                        "private": rp.get("private", False),
                        "language": rp.get("language", ""),
                    },
                )
                for rp in repos
            ]
            return ContentListResponse(items=items, has_more=len(repos) >= page_size)
        else:
            # List repo tree
            tree = await self._get_tree(path)
            items = [
                ContentItem(
                    id=e["path"], name=e["path"].split("/")[-1],
                    path=e["path"],
                    item_type="folder" if e["type"] == "tree" else "file",
                    size_bytes=e.get("size"),
                )
                for e in tree[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(tree) > page_size)
