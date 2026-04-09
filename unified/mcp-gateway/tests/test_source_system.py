from __future__ import annotations

import pytest

from .helpers import load_gateway_main


gateway = load_gateway_main()


def test_normalize_source_system_trims_and_lowercases() -> None:
    assert gateway._normalize_source_system("  CoDeX_Agent-1  ") == "codex_agent-1"


def test_normalize_source_system_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="MCP_SOURCE_SYSTEM"):
        gateway._normalize_source_system("Bad Value!")
