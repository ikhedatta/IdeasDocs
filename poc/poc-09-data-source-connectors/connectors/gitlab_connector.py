"""GitLab connector — ingest repository files, issues, and wiki pages."""

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


@register(SourceType.GITLAB)
class GitLabConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest from GitLab repositories via REST API v4."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.GITLAB,
            display_name="GitLab",
            description="Sync repository files, issues, merge requests, and wiki pages from GitLab.",
            icon="gitlab",
            category="dev_tools",
            auth_methods=[AuthMethod.API_KEY],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "base_url": {"type": "string", "default": "https://gitlab.com", "description": "GitLab instance URL"},
                "project_ids": {"type": "array", "items": "string", "description": "Project IDs or paths (URL-encoded)"},
                "include_issues": {"type": "boolean", "default": True},
                "include_wiki": {"type": "boolean", "default": True},
                "include_repo_files": {"type": "boolean", "default": True},
                "branch": {"type": "string", "default": "main"},
                "file_extensions": {"type": "array", "items": "string", "default": ["md", "txt", "rst", "py", "js", "ts"]},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        self._base = cfg.get("base_url", "https://gitlab.com").rstrip("/")
        self._project_ids: list[str] = cfg.get("project_ids", [])
        self._branch = cfg.get("branch", "main")
        self._include_issues = cfg.get("include_issues", True)
        self._include_wiki = cfg.get("include_wiki", True)
        self._include_files = cfg.get("include_repo_files", True)
        self._extensions = set(cfg.get("file_extensions", ["md", "txt", "rst"]))

        self._client = httpx.AsyncClient(
            base_url=f"{self._base}/api/v4",
            headers={"PRIVATE-TOKEN": creds["api_token"]},
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

    @staticmethod
    def _encode_path(project_id: str) -> str:
        import urllib.parse
        return urllib.parse.quote(project_id, safe="")

    async def _get_repo_tree(self, pid: str, path: str = "", page: int = 1) -> list[dict]:
        r = await self._client.get(
            f"/projects/{self._encode_path(pid)}/repository/tree",
            params={"ref": self._branch, "path": path, "per_page": 100, "page": page, "recursive": True},
        )
        r.raise_for_status()
        return r.json()

    async def _get_file_content(self, pid: str, file_path: str) -> bytes:
        import urllib.parse
        encoded = urllib.parse.quote(file_path, safe="")
        r = await self._client.get(
            f"/projects/{self._encode_path(pid)}/repository/files/{encoded}",
            params={"ref": self._branch},
        )
        r.raise_for_status()
        data = r.json()
        return base64.b64decode(data.get("content", ""))

    async def _get_issues(self, pid: str, updated_after: str = "", page: int = 1) -> list[dict]:
        params: dict[str, Any] = {"per_page": 50, "page": page}
        if updated_after:
            params["updated_after"] = updated_after
        r = await self._client.get(f"/projects/{self._encode_path(pid)}/issues", params=params)
        r.raise_for_status()
        return r.json()

    def _file_to_doc(self, pid: str, tree_entry: dict, content: bytes) -> SourceDocument:
        path = tree_entry["path"]
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        return SourceDocument(
            source_id=f"gitlab:{pid}:{path}",
            source_type=SourceType.GITLAB,
            connector_id=self.config.id,
            title=path,
            content=content,
            extension=ext,
            url=f"{self._base}/{pid}/-/blob/{self._branch}/{path}",
            metadata={"project": pid, "branch": self._branch, "path": path},
        )

    def _issue_to_doc(self, pid: str, issue: dict) -> SourceDocument:
        title = issue.get("title", "")
        desc = issue.get("description", "") or ""
        text = f"# {title}\n\n{desc}"
        return SourceDocument(
            source_id=f"gitlab:{pid}:issue:{issue['iid']}",
            source_type=SourceType.GITLAB,
            connector_id=self.config.id,
            title=f"Issue #{issue['iid']}: {title}",
            content=text.encode("utf-8"),
            mime_type="text/markdown",
            extension="md",
            url=issue.get("web_url", ""),
            updated_at=issue.get("updated_at"),
            metadata={"project": pid, "state": issue.get("state"), "labels": issue.get("labels", [])},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        for pid in self._project_ids:
            # Repo files
            if self._include_files:
                tree = await self._get_repo_tree(pid)
                batch: list[SourceDocument] = []
                for entry in tree:
                    if entry["type"] != "blob":
                        continue
                    ext = entry["path"].rsplit(".", 1)[-1] if "." in entry["path"] else ""
                    if self._extensions and ext not in self._extensions:
                        continue
                    try:
                        content = await self._get_file_content(pid, entry["path"])
                        batch.append(self._file_to_doc(pid, entry, content))
                    except Exception as exc:
                        logger.warning("GitLab file download failed: %s", exc)
                    if len(batch) >= 50:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            # Issues
            if self._include_issues:
                page = 1
                while True:
                    issues = await self._get_issues(pid, page=page)
                    if not issues:
                        break
                    yield [self._issue_to_doc(pid, i) for i in issues]
                    page += 1

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        for pid in self._project_ids:
            if self._include_issues:
                page = 1
                while True:
                    issues = await self._get_issues(pid, updated_after=start.isoformat(), page=page)
                    if not issues:
                        break
                    filtered = [i for i in issues if i.get("updated_at", "") < end.isoformat()]
                    if filtered:
                        yield [self._issue_to_doc(pid, i) for i in filtered]
                    page += 1
        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            # List user's projects
            r = await self._client.get("/projects", params={"membership": True, "per_page": page_size})
            r.raise_for_status()
            projects = r.json()
            items = [
                ContentItem(
                    id=str(p["id"]), name=p.get("path_with_namespace", ""),
                    path=str(p["id"]), item_type="repo",
                    metadata={"description": p.get("description", ""), "visibility": p.get("visibility")},
                )
                for p in projects
            ]
            return ContentListResponse(items=items, has_more=len(projects) >= page_size)
        else:
            # List repo tree
            tree = await self._get_repo_tree(path)
            items = [
                ContentItem(
                    id=e["path"], name=e["name"],
                    path=e["path"],
                    item_type="folder" if e["type"] == "tree" else "file",
                )
                for e in tree[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(tree) > page_size)
