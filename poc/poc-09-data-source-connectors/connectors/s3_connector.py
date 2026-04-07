"""Amazon S3 connector — list and ingest objects from S3 buckets."""

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


@register(SourceType.S3)
class S3Connector(BaseConnector, LoadConnector, PollConnector, BrowsableConnector):
    """Ingest files from Amazon S3 (or any S3-compatible store)."""

    @classmethod
    def source_info(cls) -> SourceInfo:
        return SourceInfo(
            source_type=SourceType.S3,
            display_name="Amazon S3",
            description="Ingest documents from S3 buckets. Supports access-key, IAM role, and assume-role auth.",
            icon="cloud",
            category="cloud_storage",
            auth_methods=[AuthMethod.ACCESS_KEY, AuthMethod.SERVICE_ACCOUNT],
            default_auth=AuthMethod.ACCESS_KEY,
            config_schema={
                "bucket": {"type": "string", "required": True, "description": "S3 bucket name"},
                "prefix": {"type": "string", "required": False, "description": "Key prefix filter", "default": ""},
                "region": {"type": "string", "required": False, "default": "us-east-1"},
                "endpoint_url": {"type": "string", "required": False, "description": "Custom endpoint for S3-compatible stores"},
                "file_extensions": {"type": "array", "items": "string", "description": "Allowed extensions (empty = all)"},
            },
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        import boto3

        creds = self.config.credentials
        cfg = self.config.config
        kwargs: dict[str, Any] = {"region_name": cfg.get("region", "us-east-1")}
        if cfg.get("endpoint_url"):
            kwargs["endpoint_url"] = cfg["endpoint_url"]
        if self.config.auth_method == AuthMethod.ACCESS_KEY:
            kwargs["aws_access_key_id"] = creds["access_key_id"]
            kwargs["aws_secret_access_key"] = creds["secret_access_key"]

        self._client = boto3.client("s3", **kwargs)
        self._bucket = cfg["bucket"]
        self._prefix = cfg.get("prefix", "")
        self._extensions = set(cfg.get("file_extensions", []))
        logger.info("S3 connected: bucket=%s prefix=%s", self._bucket, self._prefix)

    async def disconnect(self) -> None:
        self._client = None

    async def validate(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except Exception as exc:
            logger.error("S3 validation failed: %s", exc)
            return False

    # ── Helpers ─────────────────────────────────────────────────────

    def _should_include(self, key: str) -> bool:
        if not self._extensions:
            return True
        return any(key.lower().endswith(f".{ext}") for ext in self._extensions)

    def _obj_to_doc(self, obj: dict, body: bytes) -> SourceDocument:
        key = obj["Key"]
        ext = key.rsplit(".", 1)[-1] if "." in key else ""
        return SourceDocument(
            source_id=key,
            source_type=SourceType.S3,
            connector_id=self.config.id,
            title=key.split("/")[-1],
            content=body,
            extension=ext,
            size_bytes=obj.get("Size", len(body)),
            url=f"s3://{self._bucket}/{key}",
            updated_at=obj.get("LastModified"),
            metadata={"bucket": self._bucket, "key": key, "etag": obj.get("ETag", "")},
        )

    # ── LoadConnector ──────────────────────────────────────────────

    async def load_from_state(self) -> Generator[list[SourceDocument], None, None]:
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self._prefix)
        batch: list[SourceDocument] = []

        for page in pages:
            for obj in page.get("Contents", []):
                if not self._should_include(obj["Key"]):
                    continue
                resp = self._client.get_object(Bucket=self._bucket, Key=obj["Key"])
                body = resp["Body"].read()
                batch.append(self._obj_to_doc(obj, body))
                if len(batch) >= 50:
                    yield batch
                    batch = []
        if batch:
            yield batch

    # ── PollConnector ──────────────────────────────────────────────

    async def poll_source(
        self, start: datetime, end: datetime, checkpoint: Optional[SyncCheckpoint] = None
    ) -> Generator[list[SourceDocument], None, SyncCheckpoint]:
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self._prefix)
        batch: list[SourceDocument] = []
        max_modified = start

        for page in pages:
            for obj in page.get("Contents", []):
                modified = obj.get("LastModified")
                if modified and (modified < start or modified >= end):
                    continue
                if not self._should_include(obj["Key"]):
                    continue
                resp = self._client.get_object(Bucket=self._bucket, Key=obj["Key"])
                body = resp["Body"].read()
                batch.append(self._obj_to_doc(obj, body))
                if modified and modified > max_modified:
                    max_modified = modified
                if len(batch) >= 50:
                    yield batch
                    batch = []
        if batch:
            yield batch

        return SyncCheckpoint(last_sync_end=max_modified)

    # ── BrowsableConnector ─────────────────────────────────────────

    async def list_content(
        self, path: str = "", cursor: Optional[str] = None, page_size: int = 50
    ) -> ContentListResponse:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": path or self._prefix,
            "Delimiter": "/",
            "MaxKeys": page_size,
        }
        if cursor:
            kwargs["ContinuationToken"] = cursor

        resp = self._client.list_objects_v2(**kwargs)
        items: list[ContentItem] = []

        # Folders (common prefixes)
        for prefix in resp.get("CommonPrefixes", []):
            p = prefix["Prefix"]
            items.append(ContentItem(
                id=p, name=p.rstrip("/").split("/")[-1],
                path=p, item_type="folder", selectable=True,
            ))

        # Files
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if key == (path or self._prefix):
                continue
            items.append(ContentItem(
                id=key, name=key.split("/")[-1],
                path=key, item_type="file",
                size_bytes=obj.get("Size"), updated_at=obj.get("LastModified"),
            ))

        return ContentListResponse(
            items=items,
            cursor=resp.get("NextContinuationToken"),
            has_more=resp.get("IsTruncated", False),
        )
