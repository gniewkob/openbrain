from __future__ import annotations

import sys
from pathlib import Path

from src import mcp_transport
from src.runtime_limits import load_runtime_limits

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_TESTS = ROOT / "mcp-gateway" / "tests"
if str(GATEWAY_TESTS) not in sys.path:
    sys.path.insert(0, str(GATEWAY_TESTS))

from helpers import load_gateway_main  # noqa: E402

try:
    _gateway = load_gateway_main()
    _GATEWAY_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - import environment dependent
    _gateway = None
    _GATEWAY_IMPORT_ERROR = exc


def test_runtime_limits_loads_expected_keys() -> None:
    limits = load_runtime_limits()
    assert limits["max_search_top_k"] >= 1
    assert limits["max_list_limit"] >= 1
    assert limits["max_sync_limit"] >= 1
    assert limits["max_bulk_items"] >= 1


def test_runtime_limits_match_transport_constants() -> None:
    limits = load_runtime_limits()
    assert mcp_transport.MAX_SEARCH_TOP_K == limits["max_search_top_k"]
    assert mcp_transport.MAX_LIST_LIMIT == limits["max_list_limit"]
    assert mcp_transport.MAX_SYNC_LIMIT == limits["max_sync_limit"]
    assert mcp_transport.MAX_BULK_ITEMS == limits["max_bulk_items"]


def test_runtime_limits_match_gateway_constants_when_available() -> None:
    if _GATEWAY_IMPORT_ERROR is not None:
        return

    limits = load_runtime_limits()
    assert _gateway.MAX_SEARCH_TOP_K == limits["max_search_top_k"]
    assert _gateway.MAX_LIST_LIMIT == limits["max_list_limit"]
    assert _gateway.MAX_SYNC_LIMIT == limits["max_sync_limit"]
