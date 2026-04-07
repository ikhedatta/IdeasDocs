"""Sync engine — orchestrates connector execution with checkpointing and logging."""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional

from interfaces import BaseConnector, LoadConnector, PollConnector
from models import ConnectorConfig, SyncCheckpoint, SyncLog, SyncStatus
from registry import create_connector

logger = logging.getLogger(__name__)


class SyncEngine:
    """Execute sync tasks, track state, and emit logs."""

    def __init__(self, max_concurrent: int = 4, timeout_seconds: int = 600) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        # In-memory state (swap for DB in production)
        self._logs: dict[str, list[SyncLog]] = {}  # connector_id → logs
        self._checkpoints: dict[str, SyncCheckpoint] = {}  # connector_id → checkpoint
        self._running: set[str] = set()

    # ── Public API ─────────────────────────────────────────────────

    async def trigger_sync(
        self,
        config: ConnectorConfig,
        full_reindex: bool = False,
    ) -> SyncLog:
        """Start a sync task for the given connector config."""
        if config.id in self._running:
            raise RuntimeError(f"Sync already running for connector {config.id}")

        log = SyncLog(connector_id=config.id, status=SyncStatus.SCHEDULED)
        self._add_log(config.id, log)

        # Fire and forget (bounded by semaphore)
        asyncio.create_task(self._execute(config, log, full_reindex))
        return log

    async def cancel_sync(self, connector_id: str) -> bool:
        """Mark a running sync as cancelled (cooperative cancellation)."""
        if connector_id in self._running:
            self._running.discard(connector_id)
            # Update latest log
            logs = self._logs.get(connector_id, [])
            if logs and logs[-1].status == SyncStatus.RUNNING:
                logs[-1].status = SyncStatus.CANCELLED
                logs[-1].finished_at = datetime.utcnow()
            return True
        return False

    def get_logs(self, connector_id: str, limit: int = 20) -> list[SyncLog]:
        return list(reversed(self._logs.get(connector_id, [])))[:limit]

    def get_checkpoint(self, connector_id: str) -> Optional[SyncCheckpoint]:
        return self._checkpoints.get(connector_id)

    def get_latest_log(self, connector_id: str) -> Optional[SyncLog]:
        logs = self._logs.get(connector_id, [])
        return logs[-1] if logs else None

    def is_running(self, connector_id: str) -> bool:
        return connector_id in self._running

    # ── Internal execution ─────────────────────────────────────────

    async def _execute(
        self, config: ConnectorConfig, log: SyncLog, full_reindex: bool
    ) -> None:
        async with self._semaphore:
            self._running.add(config.id)
            log.status = SyncStatus.RUNNING
            log.started_at = datetime.utcnow()

            connector: Optional[BaseConnector] = None
            try:
                connector = create_connector(config)
                await connector.connect()
                valid = await connector.validate()
                if not valid:
                    raise ConnectionError("Connector validation failed — check credentials")

                timeout = config.timeout_seconds or self._timeout
                await asyncio.wait_for(
                    self._run_sync(connector, config, log, full_reindex),
                    timeout=timeout,
                )

                log.status = SyncStatus.DONE
                logger.info(
                    "Sync complete: connector=%s fetched=%d new=%d updated=%d",
                    config.id, log.docs_fetched, log.docs_new, log.docs_updated,
                )

            except asyncio.TimeoutError:
                log.status = SyncStatus.FAILED
                log.error_message = f"Sync timed out after {config.timeout_seconds}s"
                logger.error("Sync timeout: connector=%s", config.id)

            except asyncio.CancelledError:
                log.status = SyncStatus.CANCELLED
                logger.info("Sync cancelled: connector=%s", config.id)

            except Exception as exc:
                log.status = SyncStatus.FAILED
                log.error_message = str(exc)
                log.error_trace = traceback.format_exc()
                logger.error("Sync failed: connector=%s error=%s", config.id, exc)

            finally:
                log.finished_at = datetime.utcnow()
                self._running.discard(config.id)
                if connector:
                    try:
                        await connector.disconnect()
                    except Exception:
                        pass

    async def _run_sync(
        self,
        connector: BaseConnector,
        config: ConnectorConfig,
        log: SyncLog,
        full_reindex: bool,
    ) -> None:
        """Core sync logic — dispatches to load or poll based on state."""
        checkpoint = self._checkpoints.get(config.id)

        if full_reindex or checkpoint is None:
            # Full load
            if not isinstance(connector, LoadConnector):
                raise TypeError(f"Connector {config.source_type} does not support full load")

            async for batch in connector.load_from_state():
                if config.id not in self._running:
                    break  # Cooperative cancellation
                log.docs_fetched += len(batch)
                log.docs_new += len(batch)
                # In production: forward batch to document processing pipeline
                logger.debug("Batch: %d docs from %s", len(batch), config.source_type)

            self._checkpoints[config.id] = SyncCheckpoint(
                last_sync_start=log.started_at,
                last_sync_end=datetime.utcnow(),
            )
        else:
            # Incremental poll
            if not isinstance(connector, PollConnector):
                raise TypeError(f"Connector {config.source_type} does not support incremental poll")

            start = checkpoint.last_sync_end or checkpoint.last_sync_start or log.started_at
            end = datetime.utcnow()

            result_checkpoint = None
            async for batch in connector.poll_source(start, end, checkpoint):
                if config.id not in self._running:
                    break
                log.docs_fetched += len(batch)
                log.docs_updated += len(batch)
                logger.debug("Poll batch: %d docs from %s", len(batch), config.source_type)

            # Update checkpoint
            self._checkpoints[config.id] = SyncCheckpoint(
                last_sync_start=start,
                last_sync_end=end,
                cursor=checkpoint.cursor,
            )

        log.checkpoint = self._checkpoints[config.id]

    # ── Storage helpers ────────────────────────────────────────────

    def _add_log(self, connector_id: str, log: SyncLog) -> None:
        if connector_id not in self._logs:
            self._logs[connector_id] = []
        self._logs[connector_id].append(log)
        # Keep last 100 logs per connector
        if len(self._logs[connector_id]) > 100:
            self._logs[connector_id] = self._logs[connector_id][-100:]
