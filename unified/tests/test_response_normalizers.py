from __future__ import annotations

from src.response_normalizers import (
    normalize_find_hits_to_records,
    normalize_find_hits_to_scored_memories,
)


def test_normalize_find_hits_to_records_uses_record_field() -> None:
    hits = [{"record": {"id": "mem-1", "domain": "build"}, "score": 0.9}]
    records = normalize_find_hits_to_records(hits)
    assert records[0]["id"] == "mem-1"
    assert records[0]["domain"] == "build"


def test_normalize_find_hits_to_scored_memories_maps_memory_key() -> None:
    hits = [{"record": {"id": "mem-1", "domain": "build"}, "score": 0.9}]
    scored = normalize_find_hits_to_scored_memories(hits)
    assert scored[0]["score"] == 0.9
    assert scored[0]["memory"]["id"] == "mem-1"
    assert scored[0]["memory"]["domain"] == "build"


def test_normalize_find_hits_normalizes_actor_fields() -> None:
    hits = [
        {
            "record": {
                "id": "mem-1",
                "domain": "build",
                "created_by": "  creator  ",
                "updated_by": "   ",
            },
            "score": 0.9,
        }
    ]
    records = normalize_find_hits_to_records(hits)
    scored = normalize_find_hits_to_scored_memories(hits)
    assert records[0]["created_by"] == "creator"
    assert records[0]["updated_by"] == "creator"
    assert scored[0]["memory"]["created_by"] == "creator"
    assert scored[0]["memory"]["updated_by"] == "creator"
