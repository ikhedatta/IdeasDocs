"""Data models for the connector framework."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    S3 = "s3"
    CONFLUENCE = "confluence"
    DISCORD = "discord"
    GOOGLE_DRIVE = "google_drive"
    GMAIL = "gmail"
    JIRA = "jira"
    DROPBOX = "dropbox"
    GCS = "gcs"
    GITLAB = "gitlab"
    GITHUB = "github"
    BITBUCKET = "bitbucket"
    ZENDESK = "zendesk"
    ASANA = "asana"


class AuthMethod(str, Enum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    ACCESS_KEY = "access_key"
    SERVICE_ACCOUNT = "service_account"
    BOT_TOKEN = "bot_token"
    BASIC = "basic"
    APP_PASSWORD = "app_password"


class SyncStatus(str, Enum):
    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


# ── Source Metadata ────────────────────────────────────────────────────

class SourceInfo(BaseModel):
    """Static metadata about a data source type."""
    source_type: SourceType
    display_name: str
    description: str
    icon: str  # Lucide icon name
    category: str  # "cloud_storage", "collaboration", "dev_tools", "communication", "project_management"
    auth_methods: list[AuthMethod]
    default_auth: AuthMethod
    config_schema: dict[str, Any] = Field(default_factory=dict)


# ── Documents ──────────────────────────────────────────────────────────

class SourceDocument(BaseModel):
    """A document fetched from an external source."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source_id: str  # ID in the external system
    source_type: SourceType
    connector_id: str
    title: str
    content: bytes = b""
    mime_type: str = "application/octet-stream"
    extension: str = ""
    url: Optional[str] = None
    size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    permissions: Optional[ExternalAccess] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class ExternalAccess(BaseModel):
    """Permission model for source documents."""
    is_public: bool = False
    user_emails: set[str] = Field(default_factory=set)
    group_ids: set[str] = Field(default_factory=set)


# ── Connector Configuration ───────────────────────────────────────────

class ConnectorConfig(BaseModel):
    """User-supplied configuration for a connector instance."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    source_type: SourceType
    auth_method: AuthMethod
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    kb_id: Optional[str] = None
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    refresh_interval_minutes: int = 60
    timeout_seconds: int = 600
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Sync State ─────────────────────────────────────────────────────────

class SyncCheckpoint(BaseModel):
    """Persisted state for incremental sync."""
    last_sync_start: Optional[datetime] = None
    last_sync_end: Optional[datetime] = None
    cursor: Optional[str] = None  # Source-specific pagination cursor
    extra: dict[str, Any] = Field(default_factory=dict)


class SyncLog(BaseModel):
    """Execution record for a sync run."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    connector_id: str
    status: SyncStatus = SyncStatus.SCHEDULED
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    docs_fetched: int = 0
    docs_new: int = 0
    docs_updated: int = 0
    docs_failed: int = 0
    error_message: Optional[str] = None
    error_trace: Optional[str] = None
    checkpoint: SyncCheckpoint = Field(default_factory=SyncCheckpoint)


# ── API Request / Response ─────────────────────────────────────────────

class CreateConnectorRequest(BaseModel):
    name: str
    source_type: SourceType
    auth_method: AuthMethod
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    kb_id: Optional[str] = None
    refresh_interval_minutes: int = 60


class UpdateConnectorRequest(BaseModel):
    name: Optional[str] = None
    credentials: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    kb_id: Optional[str] = None
    refresh_interval_minutes: Optional[int] = None
    status: Optional[ConnectorStatus] = None


class ConnectorResponse(BaseModel):
    connector: ConnectorConfig
    last_sync: Optional[SyncLog] = None
    source_info: Optional[SourceInfo] = None


class ContentItem(BaseModel):
    """An item in the content browser (file, page, channel, etc.)."""
    id: str
    name: str
    path: str = ""
    item_type: str = "file"  # file, folder, page, channel, repo, space, project
    size_bytes: Optional[int] = None
    updated_at: Optional[datetime] = None
    children_count: Optional[int] = None
    selectable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentListResponse(BaseModel):
    items: list[ContentItem]
    cursor: Optional[str] = None
    has_more: bool = False
