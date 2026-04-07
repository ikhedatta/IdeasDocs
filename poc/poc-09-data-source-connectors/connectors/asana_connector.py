"""Asana connector — ingest tasks and project notes from Asana."""

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

ASANA_API = "https://app.asana.com/api/1.0"


@register(SourceType.ASANA)
class AsanaConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest tasks and project descriptions from Asana."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.ASANA,
            display_name="Asana",
            description="Sync tasks, project notes, and comments from Asana workspaces.",
            icon="list-checks",
            category="project_management",
            auth_methods=[AuthMethod.API_KEY, AuthMethod.OAUTH2],
            default_auth=AuthMethod.API_KEY,
            config_schema={
                "workspace_gid": {"type": "string", "required": True, "description": "Asana workspace GID"},
                "project_gids": {"type": "array", "items": "string", "description": "Projects to sync (empty = all)"},
                "include_comments": {"type": "boolean", "default": True},
                "include_subtasks": {"type": "boolean", "default": False},
            },
        )

    async def connect(self) -> None:
        import httpx

        creds = self.config.credentials
        cfg = self.config.config
        token = creds.get("access_token") or creds.get("api_key", "")
        self._workspace_gid = cfg["workspace_gid"]
        self._project_gids: list[str] = cfg.get("project_gids", [])
        self._include_comments = cfg.get("include_comments", True)

        self._client = httpx.AsyncClient(
            base_url=ASANA_API,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get("/users/me")
            return r.status_code == 200
        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_projects(self) -> list[dict]:
        if self._project_gids:
            projects = []
            for gid in self._project_gids:
                r = await self._client.get(f"/projects/{gid}")
                r.raise_for_status()
                projects.append(r.json()["data"])
            return projects
        r = await self._client.get(
            "/projects",
            params={"workspace": self._workspace_gid, "limit": 100,
                    "opt_fields": "name,notes,modified_at,permalink_url"},
        )
        r.raise_for_status()
        return r.json().get("data", [])

    async def _get_tasks(self, project_gid: str, modified_since: str = "", offset: str = "") -> dict:
        params: dict[str, Any] = {
            "project": project_gid,
            "limit": 50,
            "opt_fields": "name,notes,completed,assignee.name,modified_at,permalink_url,tags.name",
        }
        if modified_since:
            params["modified_since"] = modified_since
        if offset:
            params["offset"] = offset
        r = await self._client.get("/tasks", params=params)
        r.raise_for_status()
        return r.json()

    async def _get_stories(self, task_gid: str) -> list[dict]:
        """Get task comments (stories of type 'comment')."""
        r = await self._client.get(
            f"/tasks/{task_gid}/stories",
            params={"opt_fields": "text,created_by.name,created_at,type"},
        )
        r.raise_for_status()
        stories = r.json().get("data", [])
        return [s for s in stories if s.get("type") == "comment"]

    def _task_to_doc(self, project_name: str, task: dict, comments_text: str = "") -> SourceDocument:
        name = task.get("name", "Untitled")
        notes = task.get("notes", "") or ""
        assignee = (task.get("assignee") or {}).get("name", "unassigned")
        tags = [t.get("name", "") for t in task.get("tags", [])]
        status = "Done" if task.get("completed") else "Open"

        text = f"# {name}\n\nProject: {project_name}\nAssignee: {assignee}\nStatus: {status}\nTags: {', '.join(tags)}\n\n{notes}"
        if comments_text:
            text += f"\n\n## Comments\n{comments_text}"

        return SourceDocument(
            source_id=f"asana:task:{task['gid']}",
            source_type=SourceType.ASANA,
            connector_id=self.config.id,
            title=f"{project_name} / {name}",
            content=text.encode("utf-8"),
            mime_type="text/markdown",
            extension="md",
            url=task.get("permalink_url", ""),
            updated_at=task.get("modified_at"),
            metadata={
                "project": project_name,
                "assignee": assignee,
                "completed": task.get("completed", False),
                "tags": tags,
            },
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        projects = await self._get_projects()
        for proj in projects:
            proj_name = proj.get("name", "")
            offset = ""
            while True:
                data = await self._get_tasks(proj["gid"], offset=offset)
                tasks = data.get("data", [])
                if not tasks:
                    break
                batch: list[SourceDocument] = []
                for task in tasks:
                    comments_text = ""
                    if self._include_comments:
                        try:
                            comments = await self._get_stories(task["gid"])
                            for c in comments:
                                author = c.get("created_by", {}).get("name", "")
                                comments_text += f"\n---\n**{author}**: {c.get('text', '')}\n"
                        except Exception:
                            pass
                    batch.append(self._task_to_doc(proj_name, task, comments_text))
                if batch:
                    yield batch
                next_page = data.get("next_page")
                if not next_page or not next_page.get("offset"):
                    break
                offset = next_page["offset"]

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        projects = await self._get_projects()
        for proj in projects:
            proj_name = proj.get("name", "")
            offset = ""
            while True:
                data = await self._get_tasks(proj["gid"], modified_since=start.isoformat(), offset=offset)
                tasks = data.get("data", [])
                if not tasks:
                    break
                filtered = [t for t in tasks if t.get("modified_at", "") < end.isoformat()]
                if filtered:
                    yield [self._task_to_doc(proj_name, t) for t in filtered]
                next_page = data.get("next_page")
                if not next_page or not next_page.get("offset"):
                    break
                offset = next_page["offset"]

        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        if not path:
            projects = await self._get_projects()
            items = [
                ContentItem(
                    id=p["gid"], name=p.get("name", ""),
                    path=p["gid"], item_type="project",
                    metadata={"notes": (p.get("notes") or "")[:200]},
                )
                for p in projects[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(projects) > page_size)
        else:
            # List tasks in project
            data = await self._get_tasks(path)
            tasks = data.get("data", [])
            items = [
                ContentItem(
                    id=t["gid"], name=t.get("name", ""),
                    path=t["gid"], item_type="file",
                    metadata={"completed": t.get("completed", False)},
                )
                for t in tasks[:page_size]
            ]
            return ContentListResponse(items=items, has_more=len(tasks) > page_size)
