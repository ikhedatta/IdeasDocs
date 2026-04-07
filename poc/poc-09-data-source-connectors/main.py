"""POC-09 — Data Source Connectors API.

FastAPI application providing CRUD for data source connectors,
content browsing, sync triggering, and OAuth flows.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import DATA_DIR, HOST, PORT
from models import (
    ConnectorResponse,
    ConnectorStatus,
    ContentListResponse,
    CreateConnectorRequest,
    SourceType,
    UpdateConnectorRequest,
)
from registry import get_source_info, list_available_sources
from store import ConnectorStore
from sync_engine import SyncEngine

# Trigger connector registration
import connectors  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="POC-09 · Data Source Connectors",
    description="Connector framework for 13 external data sources with sync orchestration.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ConnectorStore(data_dir=DATA_DIR)
engine = SyncEngine()


# ── Source catalog ─────────────────────────────────────────────────────

@app.get("/sources")
async def list_sources():
    """List all available data source types with metadata."""
    return {"sources": [s.model_dump() for s in list_available_sources()]}


@app.get("/sources/{source_type}")
async def get_source(source_type: SourceType):
    """Get metadata for a specific source type."""
    try:
        info = get_source_info(source_type)
        return info.model_dump()
    except ValueError:
        raise HTTPException(404, f"Source type '{source_type}' not found")


# ── Connector CRUD ─────────────────────────────────────────────────────

@app.post("/connectors", status_code=201)
async def create_connector(req: CreateConnectorRequest):
    """Create a new connector instance."""
    from models import ConnectorConfig

    config = ConnectorConfig(
        name=req.name,
        source_type=req.source_type,
        auth_method=req.auth_method,
        credentials=req.credentials,
        config=req.config,
        kb_id=req.kb_id,
        refresh_interval_minutes=req.refresh_interval_minutes,
    )
    created = store.create(config)
    return ConnectorResponse(
        connector=created,
        source_info=get_source_info(created.source_type),
    ).model_dump()


@app.get("/connectors")
async def list_connectors(source_type: Optional[SourceType] = Query(None)):
    """List all connector instances (credentials masked)."""
    items = store.list_all(source_type=source_type)
    return {"connectors": items, "total": len(items)}


@app.get("/connectors/{connector_id}")
async def get_connector(connector_id: str):
    """Get a single connector with its latest sync info."""
    masked = store.get_masked(connector_id)
    if not masked:
        raise HTTPException(404, "Connector not found")
    last_sync = engine.get_latest_log(connector_id)
    return {
        "connector": masked,
        "last_sync": last_sync.model_dump() if last_sync else None,
        "source_info": get_source_info(SourceType(masked["source_type"])).model_dump(),
    }


@app.patch("/connectors/{connector_id}")
async def update_connector(connector_id: str, req: UpdateConnectorRequest):
    """Update connector config/credentials."""
    updates = req.model_dump(exclude_none=True)
    updated = store.update(connector_id, updates)
    if not updated:
        raise HTTPException(404, "Connector not found")
    return {"connector": store.get_masked(connector_id)}


@app.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str):
    """Delete a connector."""
    if engine.is_running(connector_id):
        await engine.cancel_sync(connector_id)
    deleted = store.delete(connector_id)
    if not deleted:
        raise HTTPException(404, "Connector not found")
    return {"deleted": True}


# ── Sync operations ────────────────────────────────────────────────────

@app.post("/connectors/{connector_id}/sync")
async def trigger_sync(connector_id: str, full_reindex: bool = False):
    """Start a sync for the connector."""
    config = store.get(connector_id)
    if not config:
        raise HTTPException(404, "Connector not found")
    if config.status != ConnectorStatus.ACTIVE:
        raise HTTPException(400, f"Connector is {config.status.value}, cannot sync")

    try:
        log = await engine.trigger_sync(config, full_reindex=full_reindex)
        return {"sync_log": log.model_dump()}
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/connectors/{connector_id}/cancel")
async def cancel_sync(connector_id: str):
    """Cancel a running sync."""
    cancelled = await engine.cancel_sync(connector_id)
    if not cancelled:
        raise HTTPException(404, "No running sync found")
    return {"cancelled": True}


@app.get("/connectors/{connector_id}/logs")
async def get_sync_logs(connector_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get sync logs for a connector."""
    logs = engine.get_logs(connector_id, limit)
    return {"logs": [l.model_dump() for l in logs], "total": len(logs)}


@app.get("/connectors/{connector_id}/status")
async def get_sync_status(connector_id: str):
    """Get current sync status."""
    return {
        "running": engine.is_running(connector_id),
        "checkpoint": engine.get_checkpoint(connector_id),
        "last_sync": engine.get_latest_log(connector_id),
    }


# ── Content browsing ──────────────────────────────────────────────────

@app.get("/connectors/{connector_id}/browse")
async def browse_content(
    connector_id: str,
    path: str = Query("", description="Path/folder to browse"),
    cursor: Optional[str] = Query(None),
    page_size: int = Query(50, ge=1, le=200),
):
    """Browse available content for a connector (files, folders, spaces, etc.)."""
    config = store.get(connector_id)
    if not config:
        raise HTTPException(404, "Connector not found")

    from interfaces import BrowsableConnector
    from registry import create_connector as make

    connector = make(config)
    if not isinstance(connector, BrowsableConnector):
        raise HTTPException(400, f"Source type '{config.source_type}' does not support browsing")

    try:
        await connector.connect()
        result = await connector.list_content(path=path, cursor=cursor, page_size=page_size)
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(502, f"Failed to browse: {exc}")
    finally:
        await connector.disconnect()


# ── Validate connection ───────────────────────────────────────────────

@app.post("/connectors/{connector_id}/validate")
async def validate_connector(connector_id: str):
    """Test that connector credentials are valid."""
    config = store.get(connector_id)
    if not config:
        raise HTTPException(404, "Connector not found")

    from registry import create_connector as make

    connector = make(config)
    try:
        await connector.connect()
        valid = await connector.validate()
        return {"valid": valid}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}
    finally:
        await connector.disconnect()


# ── OAuth helpers ─────────────────────────────────────────────────────

@app.get("/oauth/{source_type}/authorize")
async def oauth_authorize(source_type: SourceType, redirect_uri: str, state: str = ""):
    """Get the OAuth authorization URL for a source."""
    from interfaces import OAuthConnector
    from models import ConnectorConfig
    from registry import get_connector_class

    cls = get_connector_class(source_type)
    dummy_config = ConnectorConfig(
        name="oauth-flow", source_type=source_type,
        auth_method="oauth2", credentials={}, config={},
    )
    connector = cls(dummy_config)
    if not isinstance(connector, OAuthConnector):
        raise HTTPException(400, f"{source_type} does not support OAuth")

    url = connector.get_oauth_url(redirect_uri, state)
    return {"authorize_url": url}


@app.post("/oauth/{source_type}/callback")
async def oauth_callback(source_type: SourceType, code: str, redirect_uri: str):
    """Exchange an OAuth code for tokens."""
    from interfaces import OAuthConnector
    from models import ConnectorConfig
    from registry import get_connector_class

    cls = get_connector_class(source_type)
    dummy_config = ConnectorConfig(
        name="oauth-flow", source_type=source_type,
        auth_method="oauth2", credentials={}, config={},
    )
    connector = cls(dummy_config)
    if not isinstance(connector, OAuthConnector):
        raise HTTPException(400, f"{source_type} does not support OAuth")

    try:
        tokens = await connector.exchange_code(code, redirect_uri)
        return {"tokens": tokens}
    except Exception as exc:
        raise HTTPException(400, f"OAuth exchange failed: {exc}")


# ── Health ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from registry import registered_types
    return {"status": "ok", "registered_connectors": [t.value for t in registered_types()]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
