"""Tests for POC-09 — Data Source Connectors.

Covers: models, credentials, registry, store, sync engine,
connector source_info, and FastAPI endpoints.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Ensure POC-09 is on sys.path ──────────────────────────────────────
POC_DIR = os.path.dirname(os.path.abspath(__file__))
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)


# ═══════════════════════════════════════════════════════════════════════
# 1. MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestModels:
    """Validate Pydantic model creation, serialization, and defaults."""

    def test_source_type_enum_has_13_values(self):
        from models import SourceType
        assert len(SourceType) == 13

    def test_source_type_values(self):
        from models import SourceType
        expected = {"s3", "confluence", "discord", "google_drive", "gmail",
                    "jira", "dropbox", "gcs", "gitlab", "github",
                    "bitbucket", "zendesk", "asana"}
        actual = {st.value for st in SourceType}
        assert actual == expected

    def test_auth_method_enum(self):
        from models import AuthMethod
        assert len(AuthMethod) == 7
        assert AuthMethod.OAUTH2.value == "oauth2"

    def test_connector_config_defaults(self):
        from models import AuthMethod, ConnectorConfig, ConnectorStatus, SourceType
        cfg = ConnectorConfig(
            name="Test",
            source_type=SourceType.GITHUB,
            auth_method=AuthMethod.API_KEY,
        )
        assert cfg.status == ConnectorStatus.ACTIVE
        assert cfg.refresh_interval_minutes == 60
        assert cfg.timeout_seconds == 600
        assert cfg.id  # auto-generated
        assert cfg.credentials == {}
        assert cfg.config == {}

    def test_connector_config_serialization(self):
        from models import AuthMethod, ConnectorConfig, SourceType
        cfg = ConnectorConfig(
            name="My S3",
            source_type=SourceType.S3,
            auth_method=AuthMethod.ACCESS_KEY,
            credentials={"access_key_id": "abc"},
            config={"bucket": "test-bucket"},
        )
        data = cfg.model_dump(mode="json")
        assert data["name"] == "My S3"
        assert data["source_type"] == "s3"
        assert data["credentials"]["access_key_id"] == "abc"

        # Round-trip
        restored = ConnectorConfig(**data)
        assert restored.name == cfg.name
        assert restored.source_type == cfg.source_type

    def test_source_document_defaults(self):
        from models import SourceDocument, SourceType
        doc = SourceDocument(
            source_id="file-123",
            source_type=SourceType.S3,
            connector_id="conn-1",
            title="test.pdf",
        )
        assert doc.content == b""
        assert doc.mime_type == "application/octet-stream"
        assert doc.metadata == {}
        assert doc.fetched_at is not None

    def test_sync_log_defaults(self):
        from models import SyncLog, SyncStatus
        log = SyncLog(connector_id="c1")
        assert log.status == SyncStatus.SCHEDULED
        assert log.docs_fetched == 0
        assert log.docs_new == 0
        assert log.error_message is None

    def test_sync_checkpoint_defaults(self):
        from models import SyncCheckpoint
        cp = SyncCheckpoint()
        assert cp.last_sync_start is None
        assert cp.cursor is None

    def test_content_item(self):
        from models import ContentItem
        item = ContentItem(id="f1", name="folder1", path="/folder1", item_type="folder")
        assert item.selectable is True
        assert item.metadata == {}

    def test_content_list_response(self):
        from models import ContentItem, ContentListResponse
        resp = ContentListResponse(
            items=[ContentItem(id="1", name="a", path="a")],
            has_more=True,
            cursor="next-page",
        )
        assert len(resp.items) == 1
        assert resp.has_more is True

    def test_create_connector_request(self):
        from models import CreateConnectorRequest
        req = CreateConnectorRequest(
            name="Test", source_type="github", auth_method="api_key",
            credentials={"api_token": "ghp_xxx"}, config={"repos": ["a/b"]},
        )
        assert req.refresh_interval_minutes == 60

    def test_update_connector_request_optional_fields(self):
        from models import UpdateConnectorRequest
        req = UpdateConnectorRequest()
        assert req.name is None
        assert req.credentials is None
        assert req.status is None

    def test_external_access_defaults(self):
        from models import ExternalAccess
        ea = ExternalAccess()
        assert ea.is_public is False
        assert ea.user_emails == set()

    def test_source_info_model(self):
        from models import AuthMethod, SourceInfo, SourceType
        info = SourceInfo(
            source_type=SourceType.S3,
            display_name="S3",
            description="test",
            icon="cloud",
            category="cloud_storage",
            auth_methods=[AuthMethod.ACCESS_KEY],
            default_auth=AuthMethod.ACCESS_KEY,
        )
        assert info.config_schema == {}


# ═══════════════════════════════════════════════════════════════════════
# 2. CREDENTIAL TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestCredentials:
    """Test encrypt/decrypt round-trip and masking."""

    def setup_method(self):
        # Reset global fernet state
        import credentials
        credentials._FERNET = None

    def test_encrypt_decrypt_roundtrip_no_key(self, monkeypatch):
        monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
        import credentials
        credentials._FERNET = None  # force re-init

        creds = {"api_token": "secret-value-12345", "email": "test@example.com"}
        token = credentials.encrypt_credentials(creds)
        assert isinstance(token, str)

        decrypted = credentials.decrypt_credentials(token)
        assert decrypted["api_token"] == "secret-value-12345"
        assert decrypted["email"] == "test@example.com"

    def test_encrypt_decrypt_roundtrip_with_fernet(self, monkeypatch):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)
        import credentials
        credentials._FERNET = None  # force re-init

        creds = {"api_token": "super-secret", "region": "us-east-1"}
        token = credentials.encrypt_credentials(creds)
        assert isinstance(token, str)
        assert "super-secret" not in token  # encrypted

        decrypted = credentials.decrypt_credentials(token)
        assert decrypted["api_token"] == "super-secret"
        assert decrypted["region"] == "us-east-1"

    def test_mask_credentials(self):
        from credentials import mask_credentials
        creds = {
            "api_token": "ghp_1234567890abcdef",
            "email": "user@example.com",
            "secret_key": "sk-abcdefghij",
            "short_token": "abc",
        }
        masked = mask_credentials(creds)
        assert masked["email"] == "user@example.com"  # not masked
        assert "****" in masked["api_token"]
        assert masked["api_token"].startswith("ghp_")
        assert masked["api_token"].endswith("cdef")
        assert "****" in masked["secret_key"]
        assert masked["short_token"] == "****"  # too short to partial-mask

    def test_mask_preserves_non_secret_keys(self):
        from credentials import mask_credentials
        creds = {"bucket": "my-bucket", "region": "us-west-2", "endpoint": "http://localhost"}
        masked = mask_credentials(creds)
        assert masked == creds  # nothing masked


# ═══════════════════════════════════════════════════════════════════════
# 3. REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestRegistry:
    """Test connector registration, lookup, and factory."""

    def setup_method(self):
        # Import connectors to trigger registration
        import connectors  # noqa: F401

    def test_all_13_connectors_registered(self):
        from registry import registered_types
        types = registered_types()
        assert len(types) == 13

    def test_list_available_sources_returns_source_info(self):
        from models import SourceInfo
        from registry import list_available_sources
        sources = list_available_sources()
        assert len(sources) == 13
        for s in sources:
            assert isinstance(s, SourceInfo)
            assert s.display_name
            assert s.description
            assert s.icon
            assert s.category
            assert len(s.auth_methods) > 0

    def test_get_connector_class_for_all_types(self):
        from interfaces import BaseConnector
        from models import SourceType
        from registry import get_connector_class
        for st in SourceType:
            cls = get_connector_class(st)
            assert issubclass(cls, BaseConnector)

    def test_get_connector_class_invalid_raises(self):
        from registry import get_connector_class
        with pytest.raises(ValueError, match="No connector registered"):
            get_connector_class("nonexistent")

    def test_create_connector_returns_instance(self):
        from interfaces import BaseConnector
        from models import AuthMethod, ConnectorConfig, SourceType
        from registry import create_connector
        config = ConnectorConfig(
            name="test", source_type=SourceType.GITHUB,
            auth_method=AuthMethod.API_KEY,
            credentials={"api_token": "test"},
            config={"repos": ["a/b"]},
        )
        connector = create_connector(config)
        assert isinstance(connector, BaseConnector)
        assert connector.config.name == "test"

    def test_get_source_info(self):
        from models import SourceType
        from registry import get_source_info
        info = get_source_info(SourceType.S3)
        assert info.source_type == SourceType.S3
        assert info.display_name == "Amazon S3"
        assert "cloud_storage" == info.category

    def test_source_categories_valid(self):
        from registry import list_available_sources
        valid_categories = {"cloud_storage", "collaboration", "communication", "dev_tools", "project_management"}
        for s in list_available_sources():
            assert s.category in valid_categories, f"{s.source_type} has invalid category: {s.category}"


# ═══════════════════════════════════════════════════════════════════════
# 4. CONNECTOR SOURCE_INFO TESTS  (verify each connector's metadata)
# ═══════════════════════════════════════════════════════════════════════

class TestConnectorMetadata:
    """Verify source_info() for each of the 13 connectors."""

    def setup_method(self):
        import connectors  # noqa: F401

    @pytest.mark.parametrize("source_type,display_name,category", [
        ("s3", "Amazon S3", "cloud_storage"),
        ("confluence", "Confluence", "collaboration"),
        ("discord", "Discord", "communication"),
        ("google_drive", "Google Drive", "cloud_storage"),
        ("gmail", "Gmail", "communication"),
        ("jira", "Jira", "project_management"),
        ("dropbox", "Dropbox", "cloud_storage"),
        ("gcs", "Google Cloud Storage", "cloud_storage"),
        ("gitlab", "GitLab", "dev_tools"),
        ("github", "GitHub", "dev_tools"),
        ("bitbucket", "Bitbucket", "dev_tools"),
        ("zendesk", "Zendesk", "collaboration"),
        ("asana", "Asana", "project_management"),
    ])
    def test_connector_source_info(self, source_type, display_name, category):
        from models import SourceType
        from registry import get_source_info
        info = get_source_info(SourceType(source_type))
        assert info.display_name == display_name
        assert info.category == category
        assert len(info.auth_methods) >= 1
        assert info.default_auth in info.auth_methods
        assert info.icon  # non-empty

    @pytest.mark.parametrize("source_type", [
        "s3", "confluence", "discord", "google_drive", "gmail",
        "jira", "dropbox", "gcs", "gitlab", "github",
        "bitbucket", "zendesk", "asana",
    ])
    def test_connector_implements_required_interfaces(self, source_type):
        from interfaces import BaseConnector, BrowsableConnector, LoadConnector, PollConnector
        from models import AuthMethod, ConnectorConfig, SourceType
        from registry import create_connector
        config = ConnectorConfig(
            name="test", source_type=SourceType(source_type),
            auth_method=AuthMethod.API_KEY,
            credentials={}, config={},
        )
        conn = create_connector(config)
        # All connectors must be BaseConnector, LoadConnector, PollConnector, BrowsableConnector
        assert isinstance(conn, BaseConnector)
        assert isinstance(conn, LoadConnector)
        assert isinstance(conn, PollConnector)
        assert isinstance(conn, BrowsableConnector)

    def test_oauth_connectors(self):
        """Google Drive, Gmail, Dropbox should implement OAuthConnector."""
        from interfaces import OAuthConnector
        from models import AuthMethod, ConnectorConfig, SourceType
        from registry import create_connector
        for st in [SourceType.GOOGLE_DRIVE, SourceType.GMAIL, SourceType.DROPBOX]:
            config = ConnectorConfig(
                name="test", source_type=st,
                auth_method=AuthMethod.OAUTH2,
                credentials={}, config={},
            )
            conn = create_connector(config)
            assert isinstance(conn, OAuthConnector), f"{st} should implement OAuthConnector"


# ═══════════════════════════════════════════════════════════════════════
# 5. STORE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestConnectorStore:
    """Test JSON-backed connector store CRUD."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_config(self, name="Test Conn", source_type="github"):
        from models import AuthMethod, ConnectorConfig, SourceType
        return ConnectorConfig(
            name=name,
            source_type=SourceType(source_type),
            auth_method=AuthMethod.API_KEY,
            credentials={"api_token": "secret-token-value-1234"},
            config={"repos": ["owner/repo"]},
        )

    def test_create_and_get(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store.create(cfg)

        retrieved = store.get(cfg.id)
        assert retrieved is not None
        assert retrieved.name == "Test Conn"
        assert retrieved.credentials["api_token"] == "secret-token-value-1234"

    def test_get_nonexistent_returns_none(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        assert store.get("nonexistent") is None

    def test_get_masked_hides_secrets(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store.create(cfg)

        masked = store.get_masked(cfg.id)
        assert masked is not None
        assert "****" in masked["credentials"]["api_token"]
        assert masked["credentials"]["api_token"] != "secret-token-value-1234"

    def test_list_all(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        store.create(self._make_config("Conn1", "github"))
        store.create(self._make_config("Conn2", "s3"))
        store.create(self._make_config("Conn3", "github"))

        all_items = store.list_all()
        assert len(all_items) == 3

    def test_list_all_filtered(self):
        from models import SourceType
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        store.create(self._make_config("Conn1", "github"))
        store.create(self._make_config("Conn2", "s3"))

        github_only = store.list_all(source_type=SourceType.GITHUB)
        assert len(github_only) == 1
        assert github_only[0]["source_type"] == "github"

    def test_update(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store.create(cfg)

        updated = store.update(cfg.id, {"name": "Renamed"})
        assert updated is not None
        assert updated.name == "Renamed"

        # Verify persisted
        reloaded = store.get(cfg.id)
        assert reloaded.name == "Renamed"

    def test_update_credentials(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store.create(cfg)

        store.update(cfg.id, {"credentials": {"api_token": "new-secret-token-5678"}})
        reloaded = store.get(cfg.id)
        assert reloaded.credentials["api_token"] == "new-secret-token-5678"

    def test_update_nonexistent_returns_none(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        assert store.update("nonexistent", {"name": "X"}) is None

    def test_delete(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store.create(cfg)

        assert store.delete(cfg.id) is True
        assert store.get(cfg.id) is None

    def test_delete_nonexistent(self):
        from store import ConnectorStore
        store = ConnectorStore(data_dir=self._tmpdir)
        assert store.delete("nonexistent") is False

    def test_persistence_across_instances(self):
        from store import ConnectorStore
        store1 = ConnectorStore(data_dir=self._tmpdir)
        cfg = self._make_config()
        store1.create(cfg)

        # New store instance reads from same file
        store2 = ConnectorStore(data_dir=self._tmpdir)
        retrieved = store2.get(cfg.id)
        assert retrieved is not None
        assert retrieved.name == cfg.name


# ═══════════════════════════════════════════════════════════════════════
# 6. SYNC ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestSyncEngine:
    """Test sync engine log tracking and state."""

    def test_initial_state(self):
        from sync_engine import SyncEngine
        engine = SyncEngine()
        assert engine.get_logs("any-id") == []
        assert engine.get_checkpoint("any-id") is None
        assert engine.get_latest_log("any-id") is None
        assert engine.is_running("any-id") is False

    @pytest.mark.asyncio
    async def test_cancel_nonrunning_returns_false(self):
        from sync_engine import SyncEngine
        engine = SyncEngine()
        result = await engine.cancel_sync("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::ResourceWarning")
    @pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
    async def test_trigger_sync_creates_log(self):
        """Trigger sync and verify the log is created (even if execution fails due to mock)."""
        from models import AuthMethod, ConnectorConfig, SourceType
        from sync_engine import SyncEngine

        engine = SyncEngine()
        config = ConnectorConfig(
            name="test", source_type=SourceType.GITHUB,
            auth_method=AuthMethod.API_KEY,
            credentials={"api_token": "fake"},
            config={"repos": ["a/b"]},
        )

        log = await engine.trigger_sync(config)
        assert log.connector_id == config.id
        # Log should exist
        assert engine.get_latest_log(config.id) is not None

        # Wait briefly for background task to complete/fail
        await asyncio.sleep(0.5)

    @pytest.mark.asyncio
    async def test_duplicate_sync_raises(self):
        """Triggering sync while one is already running should raise."""
        from models import AuthMethod, ConnectorConfig, SourceType
        from sync_engine import SyncEngine

        engine = SyncEngine()
        config = ConnectorConfig(
            name="test", source_type=SourceType.GITHUB,
            auth_method=AuthMethod.API_KEY,
            credentials={"api_token": "fake"},
            config={"repos": ["a/b"]},
        )

        # Add to running set manually
        engine._running.add(config.id)
        with pytest.raises(RuntimeError, match="already running"):
            await engine.trigger_sync(config)


# ═══════════════════════════════════════════════════════════════════════
# 7. FASTAPI ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestFastAPIEndpoints:
    """Test API endpoints using httpx TestClient."""

    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path, monkeypatch):
        """Patch store to use temp directory."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        # Re-import main to pick up patched config
        import importlib
        import config as cfg_mod
        cfg_mod.DATA_DIR = str(tmp_path)

        import main as main_mod
        main_mod.store = __import__("store").ConnectorStore(data_dir=str(tmp_path))
        main_mod.engine = __import__("sync_engine").SyncEngine()
        self.app = main_mod.app
        self.store = main_mod.store
        self.engine = main_mod.engine

    def _client(self):
        from httpx import ASGITransport, AsyncClient
        return AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

    # ── Source catalog ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_sources(self):
        async with self._client() as client:
            r = await client.get("/sources")
        assert r.status_code == 200
        data = r.json()
        assert len(data["sources"]) == 13

    @pytest.mark.asyncio
    async def test_get_source_github(self):
        async with self._client() as client:
            r = await client.get("/sources/github")
        assert r.status_code == 200
        data = r.json()
        assert data["display_name"] == "GitHub"
        assert data["category"] == "dev_tools"

    @pytest.mark.asyncio
    async def test_get_source_invalid(self):
        async with self._client() as client:
            r = await client.get("/sources/nonexistent")
        assert r.status_code == 422  # FastAPI validation error

    # ── Connector CRUD ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_connector(self):
        async with self._client() as client:
            r = await client.post("/connectors", json={
                "name": "My GitHub",
                "source_type": "github",
                "auth_method": "api_key",
                "credentials": {"api_token": "ghp_test1234567890"},
                "config": {"repos": ["owner/repo"]},
            })
        assert r.status_code == 201
        data = r.json()
        assert data["connector"]["name"] == "My GitHub"
        assert data["source_info"]["display_name"] == "GitHub"

    @pytest.mark.asyncio
    async def test_list_connectors_empty(self):
        async with self._client() as client:
            r = await client.get("/connectors")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_crud_flow(self):
        async with self._client() as client:
            # Create
            r = await client.post("/connectors", json={
                "name": "Test S3",
                "source_type": "s3",
                "auth_method": "access_key",
                "credentials": {"access_key_id": "AKIA1234", "secret_access_key": "secretkey123456"},
                "config": {"bucket": "my-bucket"},
            })
            assert r.status_code == 201
            cid = r.json()["connector"]["id"]

            # Read
            r = await client.get(f"/connectors/{cid}")
            assert r.status_code == 200
            assert r.json()["connector"]["name"] == "Test S3"
            # Credentials should be masked
            assert "****" in r.json()["connector"]["credentials"]["secret_access_key"]

            # Update
            r = await client.patch(f"/connectors/{cid}", json={"name": "Renamed S3"})
            assert r.status_code == 200
            assert r.json()["connector"]["name"] == "Renamed S3"

            # List
            r = await client.get("/connectors")
            assert r.json()["total"] == 1

            # Delete
            r = await client.delete(f"/connectors/{cid}")
            assert r.status_code == 200
            assert r.json()["deleted"] is True

            # Verify deleted
            r = await client.get(f"/connectors/{cid}")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_connector(self):
        async with self._client() as client:
            r = await client.get("/connectors/nonexistent-id")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_connector(self):
        async with self._client() as client:
            r = await client.delete("/connectors/nonexistent-id")
        assert r.status_code == 404

    # ── Sync endpoints ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_nonexistent(self):
        async with self._client() as client:
            r = await client.post("/connectors/nonexistent/sync")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_sync_logs_empty(self):
        async with self._client() as client:
            r = await client.get("/connectors/any-id/logs")
        assert r.status_code == 200
        assert r.json()["logs"] == []

    @pytest.mark.asyncio
    async def test_sync_status(self):
        async with self._client() as client:
            r = await client.get("/connectors/any-id/status")
        assert r.status_code == 200
        assert r.json()["running"] is False

    @pytest.mark.asyncio
    async def test_cancel_nonrunning(self):
        async with self._client() as client:
            r = await client.post("/connectors/any-id/cancel")
        assert r.status_code == 404

    # ── Validation ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_validate_nonexistent(self):
        async with self._client() as client:
            r = await client.post("/connectors/nonexistent/validate")
        assert r.status_code == 404

    # ── Health ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_health(self):
        async with self._client() as client:
            r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert len(data["registered_connectors"]) == 13

    # ── Filter by source type ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_connectors_filter(self):
        async with self._client() as client:
            await client.post("/connectors", json={
                "name": "GH1", "source_type": "github", "auth_method": "api_key",
                "credentials": {"api_token": "x"}, "config": {"repos": ["a/b"]},
            })
            await client.post("/connectors", json={
                "name": "S3-1", "source_type": "s3", "auth_method": "access_key",
                "credentials": {"access_key_id": "x", "secret_access_key": "y"},
                "config": {"bucket": "b"},
            })

            r = await client.get("/connectors?source_type=github")
            assert r.status_code == 200
            assert r.json()["total"] == 1
            assert r.json()["connectors"][0]["source_type"] == "github"


# ═══════════════════════════════════════════════════════════════════════
# 8. INTEGRATION TESTS (Mock external APIs)
# ═══════════════════════════════════════════════════════════════════════

class TestConnectorIntegration:
    """Test connector connect/validate with mocked HTTP clients."""

    @pytest.mark.asyncio
    async def test_github_connector_source_info(self):
        from connectors.github_connector import GitHubConnector
        info = GitHubConnector.source_info()
        assert info.source_type.value == "github"
        assert "repos" in info.config_schema

    @pytest.mark.asyncio
    async def test_s3_connector_source_info(self):
        from connectors.s3_connector import S3Connector
        info = S3Connector.source_info()
        assert info.source_type.value == "s3"
        assert "bucket" in info.config_schema
        assert info.config_schema["bucket"]["required"] is True

    @pytest.mark.asyncio
    async def test_confluence_connector_source_info(self):
        from connectors.confluence_connector import ConfluenceConnector
        info = ConfluenceConnector.source_info()
        assert info.source_type.value == "confluence"
        assert "cloud_url" in info.config_schema

    @pytest.mark.asyncio
    async def test_jira_connector_adf_to_text(self):
        from connectors.jira_connector import JiraConnector
        # Test ADF parsing
        adf = {
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello "},
                                                    {"type": "text", "text": "World"}]},
                {"type": "heading", "content": [{"type": "text", "text": "Title"}]},
            ]
        }
        result = JiraConnector._adf_to_text(adf)
        assert "Hello " in result
        assert "World" in result
        assert "Title" in result

    @pytest.mark.asyncio
    async def test_jira_adf_string_passthrough(self):
        from connectors.jira_connector import JiraConnector
        assert JiraConnector._adf_to_text("plain text") == "plain text"

    @pytest.mark.asyncio
    async def test_jira_adf_none_returns_empty(self):
        from connectors.jira_connector import JiraConnector
        assert JiraConnector._adf_to_text(None) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
