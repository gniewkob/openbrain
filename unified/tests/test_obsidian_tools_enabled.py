"""Tests for mcp_transport.py obsidian tools (lines 627-671).

These tools are only defined when ENABLE_HTTP_OBSIDIAN_TOOLS=True at module
import time. This test sets the env var and reloads the module to cover those
lines, then calls each tool's function body directly.
"""

from __future__ import annotations

import importlib
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mcp_with_obsidian_tools():
    """Yield a reloaded mcp_transport with ENABLE_HTTP_OBSIDIAN_TOOLS=True."""
    import src.mcp_transport as original_mod

    # Save state
    old_env = os.environ.get("ENABLE_HTTP_OBSIDIAN_TOOLS")
    # Remove cached module so reload picks up new env
    cached = sys.modules.pop("src.mcp_transport", None)

    os.environ["ENABLE_HTTP_OBSIDIAN_TOOLS"] = "1"
    try:
        import src.mcp_transport as reloaded_mod

        yield reloaded_mod
    finally:
        # Restore original module and env
        if cached is not None:
            sys.modules["src.mcp_transport"] = cached
        else:
            sys.modules.pop("src.mcp_transport", None)
        if old_env is None:
            os.environ.pop("ENABLE_HTTP_OBSIDIAN_TOOLS", None)
        else:
            os.environ["ENABLE_HTTP_OBSIDIAN_TOOLS"] = old_env
        # Restore the original module
        sys.modules["src.mcp_transport"] = original_mod


@pytest.mark.asyncio
async def test_brain_obsidian_vaults_calls_safe_req(mcp_with_obsidian_tools):
    """brain_obsidian_vaults → calls _safe_req GET /api/v1/obsidian/vaults (line 631)."""
    mod = mcp_with_obsidian_tools
    assert mod.ENABLE_HTTP_OBSIDIAN_TOOLS is True

    with patch.object(mod, "_safe_req", AsyncMock(return_value=["vault1"])) as mock_req:
        result = await mod.brain_obsidian_vaults()

    mock_req.assert_awaited_once_with("GET", "/api/v1/obsidian/vaults")
    assert result == ["vault1"]


@pytest.mark.asyncio
async def test_brain_obsidian_read_note_calls_safe_req(mcp_with_obsidian_tools):
    """brain_obsidian_read_note → calls _safe_req POST (lines 638-641)."""
    mod = mcp_with_obsidian_tools

    with patch.object(
        mod, "_safe_req", AsyncMock(return_value={"content": "note"})
    ) as mock_req:
        result = await mod.brain_obsidian_read_note(path="note.md", vault="MyVault")

    mock_req.assert_awaited_once_with(
        "POST",
        "/api/v1/obsidian/read-note",
        json={"vault": "MyVault", "path": "note.md"},
    )
    assert result == {"content": "note"}


@pytest.mark.asyncio
async def test_brain_obsidian_sync_calls_safe_req(mcp_with_obsidian_tools):
    """brain_obsidian_sync → validates limit, calls _safe_req POST (lines 659-671)."""
    mod = mcp_with_obsidian_tools

    with patch.object(
        mod, "_safe_req", AsyncMock(return_value={"synced": 5})
    ) as mock_req:
        result = await mod.brain_obsidian_sync(vault="V", limit=10)

    assert result == {"synced": 5}
    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["json"]["vault"] == "V"
    assert call_kwargs["json"]["limit"] == 10


@pytest.mark.asyncio
async def test_brain_obsidian_sync_invalid_limit_raises(mcp_with_obsidian_tools):
    """brain_obsidian_sync with limit=0 → ValueError (line 660)."""
    mod = mcp_with_obsidian_tools

    with pytest.raises(ValueError, match="limit must be"):
        await mod.brain_obsidian_sync(vault="V", limit=0)
