from __future__ import annotations

from typing import Any


def to_legacy_memory_shape(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "tenant_id",
        "domain",
        "entity_type",
        "content",
        "owner",
        "status",
        "version",
        "sensitivity",
        "superseded_by",
        "tags",
        "relations",
        "obsidian_ref",
        "custom_fields",
        "content_hash",
        "match_key",
        "previous_id",
        "root_id",
        "valid_from",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )
    return {key: record.get(key) for key in keys}


def normalize_find_hits_to_records(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hits:
        if isinstance(hit, dict) and isinstance(hit.get("record"), dict):
            out.append(to_legacy_memory_shape(hit["record"]))
        elif isinstance(hit, dict):
            out.append(hit)
    return out


def normalize_find_hits_to_scored_memories(
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hits:
        if isinstance(hit, dict) and "record" in hit and "score" in hit:
            out.append(
                {
                    "memory": to_legacy_memory_shape(hit["record"]),
                    "score": hit["score"],
                }
            )
        else:
            out.append(hit)
    return out
