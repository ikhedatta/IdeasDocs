"""Discord connector — ingest messages and attachments from Discord channels."""

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

DISCORD_API = "https://discord.com/api/v10"


@register(SourceType.DISCORD)
class DiscordConnector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest messages and attachments from Discord guilds via Bot API."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.DISCORD,
            display_name="Discord",
            description="Sync messages and attachments from Discord servers using a Bot token.",
            icon="message-circle",
            category="communication",
            auth_methods=[AuthMethod.BOT_TOKEN],
            default_auth=AuthMethod.BOT_TOKEN,
            config_schema={
                "guild_id": {"type": "string", "required": True, "description": "Discord server (guild) ID"},
                "channel_ids": {"type": "array", "items": "string", "description": "Channel IDs (empty = all text channels)"},
                "include_threads": {"type": "boolean", "default": False},
                "message_limit": {"type": "integer", "default": 10000, "description": "Max messages per channel per sync"},
            },
        )

    async def connect(self) -> None:
        import httpx

        token = self.config.credentials["bot_token"]
        cfg = self.config.config
        self._guild_id = cfg["guild_id"]
        self._channel_ids: list[str] = cfg.get("channel_ids", [])
        self._msg_limit = cfg.get("message_limit", 10000)

        self._client = httpx.AsyncClient(
            base_url=DISCORD_API,
            headers={"Authorization": f"Bot {token}"},
            timeout=30,
        )
        logger.info("Discord connected: guild=%s", self._guild_id)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def validate(self) -> bool:
        try:
            r = await self._client.get(f"/guilds/{self._guild_id}")
            return r.status_code == 200
        except Exception as exc:
            logger.error("Discord validation failed: %s", exc)
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_text_channels(self) -> list[dict]:
        r = await self._client.get(f"/guilds/{self._guild_id}/channels")
        r.raise_for_status()
        channels = r.json()
        # Type 0 = GUILD_TEXT
        text_channels = [c for c in channels if c["type"] == 0]
        if self._channel_ids:
            text_channels = [c for c in text_channels if c["id"] in self._channel_ids]
        return text_channels

    async def _fetch_messages(self, channel_id: str, after: str = "0", limit: int = 100) -> list[dict]:
        params: dict[str, Any] = {"limit": min(limit, 100), "after": after}
        r = await self._client.get(f"/channels/{channel_id}/messages", params=params)
        r.raise_for_status()
        return r.json()

    def _message_to_doc(self, msg: dict, channel_name: str) -> SourceDocument:
        content = msg.get("content", "")
        author = msg.get("author", {}).get("username", "unknown")
        timestamp = msg.get("timestamp", "")
        text = f"[{timestamp}] {author}: {content}"

        return SourceDocument(
            source_id=msg["id"],
            source_type=SourceType.DISCORD,
            connector_id=self.config.id,
            title=f"#{channel_name} — {msg['id']}",
            content=text.encode("utf-8"),
            mime_type="text/plain",
            extension="txt",
            metadata={"channel": channel_name, "author": author, "timestamp": timestamp},
            updated_at=datetime.fromisoformat(timestamp.replace("+00:00", "+00:00")) if timestamp else None,
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        channels = await self._get_text_channels()
        for ch in channels:
            after = "0"
            total = 0
            while total < self._msg_limit:
                messages = await self._fetch_messages(ch["id"], after=after)
                if not messages:
                    break
                docs = [self._message_to_doc(m, ch["name"]) for m in messages]
                yield docs
                total += len(messages)
                after = messages[-1]["id"]

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        # Discord snowflake timestamp approximation
        start_snowflake = str(int((start.timestamp() - 1420070400) * 1000) << 22)
        channels = await self._get_text_channels()

        for ch in channels:
            after = checkpoint.extra.get(f"ch_{ch['id']}", start_snowflake) if checkpoint else start_snowflake
            while True:
                messages = await self._fetch_messages(ch["id"], after=after)
                if not messages:
                    break
                # Filter by end time
                filtered = [m for m in messages if m.get("timestamp", "") < end.isoformat()]
                if not filtered:
                    break
                yield [self._message_to_doc(m, ch["name"]) for m in filtered]
                after = messages[-1]["id"]

        return SyncCheckpoint(last_sync_end=end)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        channels = await self._get_text_channels()
        items = [
            ContentItem(
                id=ch["id"], name=f"#{ch['name']}",
                path=ch["id"], item_type="channel",
                metadata={"topic": ch.get("topic", "")},
            )
            for ch in channels
        ]
        return ContentListResponse(items=items, has_more=False)
