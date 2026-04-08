from __future__ import annotations

from src.runtime_limits import load_runtime_limits


def test_runtime_limits_loads_expected_keys() -> None:
    limits = load_runtime_limits()
    assert limits["max_search_top_k"] >= 1
    assert limits["max_list_limit"] >= 1
    assert limits["max_sync_limit"] >= 1
    assert limits["max_bulk_items"] >= 1

