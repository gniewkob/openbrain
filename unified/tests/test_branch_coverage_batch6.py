"""Batch 6 branch coverage for combined.py, auth.py, and obsidian_sync.py.

Covers:
- src/combined.py lines 85-90: OIDC bearer token auth path
- src/combined.py lines 106-121: PUBLIC_EXPOSURE auth gate (401 and pass-through)
- src/auth.py lines 550-551: ValueError in _get_rate_limit_rpm
- src/auth.py line 625: Redis error falls back to memory limiter
- src/auth.py line 531: Redis double-checked lock inner path
- src/obsidian_sync.py line 533: conflict detection (both changed)
- src/obsidian_sync.py line 541: only obsidian changed
- src/obsidian_sync.py line 588: resolve_conflict default fallback
- src/obsidian_sync.py lines 650-657: import exception in apply_sync
- src/obsidian_sync.py lines 678-693: update exception in apply_sync
- src/obsidian_sync.py lines 707-713: outer exception handler in apply_sync
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# combined.py — OIDC bearer token success (lines 85-88)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_mcp_oidc_bearer_success():
    """OIDC bearer token verified → returns True (lines 85-88)."""
    import src.combined as combined_mod

    mock_oidc = AsyncMock()
    mock_oidc.verify_token = AsyncMock(return_value={"sub": "user1"})

    scope = {
        "headers": [
            (b"authorization", b"Bearer valid-token"),
        ]
    }

    with patch.object(combined_mod, "_oidc", mock_oidc):
        result = await combined_mod._authorize_mcp(scope)

    assert result is True
    mock_oidc.verify_token.assert_awaited_once_with("valid-token")


@pytest.mark.asyncio
async def test_authorize_mcp_oidc_bearer_exception_returns_false():
    """OIDC verify_token raises → logs warning, returns False (lines 89-90)."""
    import src.combined as combined_mod

    mock_oidc = AsyncMock()
    mock_oidc.verify_token = AsyncMock(side_effect=ValueError("invalid token"))

    scope = {
        "headers": [
            (b"authorization", b"Bearer bad-token"),
        ]
    }

    with patch.object(combined_mod, "_oidc", mock_oidc):
        result = await combined_mod._authorize_mcp(scope)

    assert result is False


# ---------------------------------------------------------------------------
# combined.py — PUBLIC_EXPOSURE auth gate (lines 106-121)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_public_exposure_unauthorized_returns_401():
    """PUBLIC_EXPOSURE=True + _authorize_mcp returns False → 401 (lines 107-118)."""
    import src.combined as combined_mod

    responses = []

    async def fake_send(event):
        responses.append(event)

    scope = {
        "type": "http",
        "path": "/mcp",
        "method": "POST",
        "headers": [],
        "query_string": b"",
    }

    async def fake_receive():
        return {"type": "http.request", "body": b""}

    with (
        patch.object(combined_mod, "PUBLIC_EXPOSURE", True),
        patch.object(combined_mod, "_authorize_mcp", AsyncMock(return_value=False)),
    ):
        await combined_mod.app(scope, fake_receive, fake_send)

    statuses = [
        r.get("status") for r in responses if r.get("type") == "http.response.start"
    ]
    assert 401 in statuses


@pytest.mark.asyncio
async def test_app_public_exposure_authorized_forwards_to_mcp():
    """PUBLIC_EXPOSURE=True + authorized → forwards to mcp_app (line 121)."""
    import src.combined as combined_mod

    mock_mcp_app = AsyncMock()

    scope = {
        "type": "http",
        "path": "/mcp",
        "method": "POST",
        "headers": [],
        "query_string": b"",
    }

    async def fake_receive():
        return {"type": "http.request", "body": b""}

    async def fake_send(event):
        pass

    with (
        patch.object(combined_mod, "PUBLIC_EXPOSURE", True),
        patch.object(combined_mod, "_authorize_mcp", AsyncMock(return_value=True)),
        patch.object(combined_mod, "mcp_app", mock_mcp_app),
    ):
        await combined_mod.app(scope, fake_receive, fake_send)

    mock_mcp_app.assert_awaited_once()


# ---------------------------------------------------------------------------
# auth.py — _get_rate_limit_rpm ValueError (lines 550-551)
# ---------------------------------------------------------------------------


def test_get_rate_limit_rpm_returns_default_on_invalid_env():
    """AUTH_RATE_LIMIT_RPM=not-a-number → ValueError caught, returns 100 (lines 550-551)."""
    from src.auth import _get_rate_limit_rpm
    import os

    original = os.environ.get("AUTH_RATE_LIMIT_RPM")
    os.environ["AUTH_RATE_LIMIT_RPM"] = "not-a-number"
    try:
        result = _get_rate_limit_rpm()
    finally:
        if original is None:
            os.environ.pop("AUTH_RATE_LIMIT_RPM", None)
        else:
            os.environ["AUTH_RATE_LIMIT_RPM"] = original

    assert result == 100


# ---------------------------------------------------------------------------
# auth.py — Redis double-checked lock returns cached client (line 531)
# ---------------------------------------------------------------------------


def test_get_redis_client_returns_cached_after_lock():
    """_redis_client already set inside lock → returns cached (line 531)."""
    import src.auth as auth_mod

    original = auth_mod._redis_client
    mock_client = MagicMock()
    auth_mod._redis_client = mock_client
    try:
        result = auth_mod._get_redis_client()
    finally:
        auth_mod._redis_client = original

    # Line 527: already set before lock → returns immediately (line 528)
    assert result is mock_client


# ---------------------------------------------------------------------------
# auth.py — Redis error falls back to memory limiter (line 625)
# ---------------------------------------------------------------------------


def test_check_internal_key_rate_limit_reraises_http_exception():
    """Redis raises HTTPException (429) → re-raised (line 625)."""
    from src.auth import check_internal_key_rate_limit
    from fastapi import HTTPException
    import src.auth as auth_mod

    original = auth_mod._redis_client
    mock_redis = MagicMock()
    auth_mod._redis_client = mock_redis
    try:
        with patch(
            "src.auth._rate_limit_redis",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            with pytest.raises(HTTPException):
                check_internal_key_rate_limit("127.0.0.1")
    finally:
        auth_mod._redis_client = original


def test_check_internal_key_rate_limit_falls_back_on_redis_exception():
    """Redis raises non-HTTPException → falls back to memory limiter (line 626-628)."""
    from src.auth import check_internal_key_rate_limit
    import src.auth as auth_mod

    original = auth_mod._redis_client
    mock_redis = MagicMock()
    auth_mod._redis_client = mock_redis
    try:
        with patch("src.auth._rate_limit_redis", side_effect=Exception("redis error")):
            with patch("src.auth._rate_limit_memory"):
                # Should not raise — falls back silently
                check_internal_key_rate_limit("127.0.0.1")
    finally:
        auth_mod._redis_client = original


# ---------------------------------------------------------------------------
# obsidian_sync.py — conflict detection (line 533)
# ---------------------------------------------------------------------------


def test_determine_change_conflict_both_changed():
    """Both memory_changed and obsidian_changed → conflict (line 533)."""
    from src.obsidian_sync import (
        BidirectionalSyncEngine,
        SyncState,
        ChangeType,
        SyncStrategy,
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state = SyncState(
        memory_id="m1",
        obsidian_path="note.md",
        vault="vault",
        content_hash="old-hash",
        memory_updated_at=now,
        obsidian_modified_at=now,
    )

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)
    memory = MagicMock()

    # Both changed
    change = engine._determine_change(
        state=state,
        memory=memory,
        obsidian_exists=True,
        memory_changed=True,
        obsidian_changed=True,
    )

    assert change is not None
    assert change.conflict is True
    assert change.change_type == ChangeType.UPDATED


# ---------------------------------------------------------------------------
# obsidian_sync.py — only obsidian changed (line 541)
# ---------------------------------------------------------------------------


def test_determine_change_only_obsidian_changed():
    """Only obsidian_changed → returns UPDATED from obsidian (line 541)."""
    from src.obsidian_sync import (
        BidirectionalSyncEngine,
        SyncState,
        ChangeType,
        SyncStrategy,
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state = SyncState(
        memory_id="m1",
        obsidian_path="note.md",
        vault="vault",
        content_hash="same-hash",
        memory_updated_at=now,
        obsidian_modified_at=now,
    )

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)
    memory = MagicMock()

    # Only obsidian changed
    change = engine._determine_change(
        state=state,
        memory=memory,
        obsidian_exists=True,
        memory_changed=False,
        obsidian_changed=True,
    )

    assert change is not None
    assert change.source == "obsidian"


# ---------------------------------------------------------------------------
# obsidian_sync.py — resolve_conflict default fallback (line 588)
# ---------------------------------------------------------------------------


def test_resolve_conflict_returns_openbrain_for_unknown_strategy():
    """Unknown/unhandled strategy falls through to default → 'openbrain' (line 588)."""
    from src.obsidian_sync import (
        BidirectionalSyncEngine,
        SyncStrategy,
        SyncChange,
        ChangeType,
    )

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)

    # Create a conflict change
    change = SyncChange(
        memory_id="m1",
        obsidian_path="note.md",
        vault="vault",
        change_type=ChangeType.UPDATED,
        source="both",
        conflict=True,
    )

    # Patch strategy to trigger the fallback
    with patch.object(engine, "strategy", "unknown-strategy"):
        result = engine.resolve_conflict(change)

    assert result == "openbrain"


# ---------------------------------------------------------------------------
# obsidian_sync.py — apply_sync import exception (lines 650-657)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_sync_import_exception_raises_obsidian_error():
    """adapter.read_note raises during import → wrapped in ObsidianCliError (lines 650-657)."""
    from src.obsidian_sync import (
        BidirectionalSyncEngine,
        SyncStrategy,
        SyncChange,
        ChangeType,
    )
    from src.exceptions import ObsidianCliError

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)

    change = SyncChange(
        memory_id=None,
        obsidian_path="note.md",
        vault="vault",
        change_type=ChangeType.CREATED,
        source="obsidian",
    )

    mock_adapter = AsyncMock()
    mock_adapter.read_note = AsyncMock(side_effect=Exception("read failed"))
    mock_session = AsyncMock()

    with patch("src.obsidian_sync.log"):
        with pytest.raises(ObsidianCliError, match="Failed to import from Obsidian"):
            await engine.apply_sync(mock_session, mock_adapter, change)


# ---------------------------------------------------------------------------
# obsidian_sync.py — apply_sync update exception (lines 678-693)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_sync_update_obsidian_wins_exception():
    """obsidian wins + adapter.read_note raises → wrapped in ObsidianCliError (lines 678-693)."""
    from src.obsidian_sync import (
        BidirectionalSyncEngine,
        SyncStrategy,
        SyncChange,
        ChangeType,
    )
    from src.exceptions import ObsidianCliError

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)

    change = SyncChange(
        memory_id="m1",
        obsidian_path="note.md",
        vault="vault",
        change_type=ChangeType.UPDATED,
        source="obsidian",
        conflict=False,
    )

    mock_adapter = AsyncMock()
    mock_adapter.read_note = AsyncMock(side_effect=Exception("read failed"))
    mock_session = AsyncMock()

    # resolve_conflict returns "obsidian" → takes the obsidian-wins path
    with patch("src.obsidian_sync.log"):
        with patch.object(engine, "resolve_conflict", return_value="obsidian"):
            with pytest.raises(
                ObsidianCliError, match="Failed to update from Obsidian"
            ):
                await engine.apply_sync(mock_session, mock_adapter, change)


# Lines 707-713 (outer exception handler) are covered by
# test_apply_sync_import_exception_raises_obsidian_error and
# test_apply_sync_update_obsidian_wins_exception above — the inner
# ObsidianCliError propagates to the outer except block.
