import os
import pytest
import importlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock


@asynccontextmanager
async def _null_db_session():
    """Async context manager that yields a no-op AsyncMock session."""
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(
        scalar_one=MagicMock(return_value=0),
        scalar_one_or_none=MagicMock(return_value=None),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        all=MagicMock(return_value=[]),
        fetchall=MagicMock(return_value=[]),
    )
    yield mock_session


class _NullSessionMaker:
    """Drop-in replacement for AsyncSessionLocal that never touches the DB."""

    def __call__(self):
        return _null_db_session()

    def __aenter__(self):
        return _null_db_session().__aenter__()

    def __aexit__(self, *args):
        return _null_db_session().__aexit__(*args)


@pytest.fixture(autouse=True, scope="session")
def global_setup():
    """Session-wide setup to ensure clean environment."""
    # Force disable public mode for all tests by default
    with patch.dict(
        os.environ,
        {
            "PUBLIC_MODE": "false",
            "PUBLIC_BASE_URL": "",
            # Prevent bidirectional-sync endpoint from hanging 120 s in unit tests
            "OBSIDIAN_SYNC_TIMEOUT_S": "2",
        },
    ):
        # Reload modules that define constants based on environment
        import src.auth
        import src.security.policy

        importlib.reload(src.auth)
        importlib.reload(src.security.policy)

        # Mock DB session globally so TestClient startup never attempts a real
        # DB connection (which would hang when Docker / the DB host is unreachable).
        null_maker = _NullSessionMaker()

        @asynccontextmanager
        async def _null_lifespan(app):
            yield

        # Stub sync result returned by the mock engine
        _stub_sync_result = MagicMock(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            changes_detected=0,
            changes_applied=0,
            conflicts=0,
            errors=[],
            details=[],
        )
        _stub_engine = AsyncMock()
        _stub_engine.sync = AsyncMock(return_value=_stub_sync_result)

        with (
            patch("src.db.AsyncSessionLocal", null_maker),
            patch("src.lifespan.AsyncSessionLocal", null_maker),
            patch(
                "src.common.obsidian_adapter.ObsidianCliAdapter._run",
                new_callable=AsyncMock,
            ) as mock_run,
            # Bypass module-level asyncio.Lock in _get_sync_engine/_get_sync_tracker;
            # those locks hang under TestClient's synthetic event loop.
            patch(
                "src.api.v1.obsidian._get_sync_engine",
                new=AsyncMock(return_value=_stub_engine),
            ),
        ):
            mock_run.return_value = ""
            yield


@pytest.fixture(autouse=True)
def disable_public_mode(monkeypatch):
    """Globally disable public mode for all tests unless explicitly enabled."""
    monkeypatch.setenv("PUBLIC_MODE", "false")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    from src import config

    config.get_config.cache_clear()

    # Also patch the constants in case they were already imported
    with (
        patch("src.auth.PUBLIC_EXPOSURE", False),
        patch("src.auth.PUBLIC_MODE", False),
        patch("src.security.policy.PUBLIC_MODE", False),
    ):
        yield
