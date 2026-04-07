"""Base connector interfaces — mixin-style ABCs inspired by RAGFlow patterns."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any, Generator, Optional

from models import (
    AuthMethod,
    ConnectorConfig,
    ContentItem,
    ContentListResponse,
    SourceDocument,
    SourceInfo,
    SyncCheckpoint,
)


class BaseConnector(abc.ABC):
    """Every connector must implement these basics."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._client: Any = None

    # ── Metadata ────────────────────────────────────────────────────

    @classmethod
    @abc.abstractmethod
    def source_info(cls) -> SourceInfo:
        """Return static metadata about this source type."""

    # ── Lifecycle ───────────────────────────────────────────────────

    @abc.abstractmethod
    async def connect(self) -> None:
        """Initialize the underlying SDK / HTTP client with credentials."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Release resources."""

    @abc.abstractmethod
    async def validate(self) -> bool:
        """Test that credentials are valid and the source is reachable."""


class LoadConnector(abc.ABC):
    """Full-load capability — fetch all documents from scratch."""

    @abc.abstractmethod
    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        """Yield batches of documents for initial indexing."""


class PollConnector(abc.ABC):
    """Incremental sync — fetch only updates since last checkpoint."""

    @abc.abstractmethod
    async def poll_source(
        self,
        start: datetime,
        end: datetime,
        checkpoint: Optional[SyncCheckpoint] = None,
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        """Yield batches of new/updated documents in [start, end) window.

        Returns the updated checkpoint when the generator is exhausted.
        """


class BrowsableConnector(abc.ABC):
    """Content browsing — let users select what to sync."""

    @abc.abstractmethod
    async def list_content(
        self,
        path: str = "",
        cursor: Optional[str] = None,
        page_size: int = 50,
    ) -> ContentListResponse:
        """List available content items (repos, folders, spaces, etc.)."""


class OAuthConnector(abc.ABC):
    """OAuth2 flow support."""

    @abc.abstractmethod
    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Build the authorization URL for the OAuth flow."""

    @abc.abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for access/refresh tokens."""

    @abc.abstractmethod
    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token."""


# ── Composite type alias ───────────────────────────────────────────────

class FullConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """A connector that supports all capabilities."""
    pass
