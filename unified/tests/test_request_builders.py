from __future__ import annotations

from src.request_builders import (
    build_find_search_payload,
    build_find_list_payload,
    build_list_filters,
    build_sync_check_payload,
    canonical_updated_by,
    normalize_updated_by,
)


def test_build_list_filters_ignores_empty_values() -> None:
    filters = build_list_filters(
        domain="build",
        entity_type=None,
        status="",
        sensitivity="internal",
        owner=None,
        tenant_id="tenant-a",
        include_test_data=False,
    )
    assert filters == {
        "domain": "build",
        "sensitivity": "internal",
        "tenant_id": "tenant-a",
    }


def test_build_list_filters_can_include_test_data_flag() -> None:
    filters = build_list_filters(domain="build", include_test_data=True)
    assert filters == {"domain": "build", "include_test_data": True}


def test_build_find_list_payload_has_contract_defaults() -> None:
    payload = build_find_list_payload(limit=5, filters={"domain": "build"})
    assert payload == {
        "query": None,
        "filters": {"domain": "build"},
        "limit": 5,
        "sort": "updated_at_desc",
    }


def test_normalize_updated_by_trims_and_falls_back() -> None:
    assert normalize_updated_by("  alice  ") == "alice"
    assert normalize_updated_by("   ") == "agent"
    assert normalize_updated_by(None) == "agent"


def test_canonical_updated_by_is_default_actor_placeholder() -> None:
    assert canonical_updated_by() == "agent"


def test_build_find_search_payload() -> None:
    payload = build_find_search_payload(
        query="auth",
        limit=7,
        filters={"domain": "build"},
    )
    assert payload == {"query": "auth", "filters": {"domain": "build"}, "limit": 7}


def test_build_sync_check_payload() -> None:
    payload = build_sync_check_payload(
        match_key="mk:1",
        file_hash="sha256:abc",
    )
    assert payload == {
        "memory_id": None,
        "match_key": "mk:1",
        "obsidian_ref": None,
        "file_hash": "sha256:abc",
    }
