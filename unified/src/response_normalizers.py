from __future__ import annotations

from typing import Any


def _normalize_actor(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def to_legacy_memory_shape(record: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize the canonical set of memory fields from a raw record dict."""
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
    normalized = {key: record.get(key) for key in keys}
    normalized_created_by = _normalize_actor(normalized.get("created_by"), "agent")
    normalized["created_by"] = normalized_created_by
    normalized["updated_by"] = _normalize_actor(
        normalized.get("updated_by"), normalized_created_by
    )
    return normalized


def normalize_find_hits_to_records(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten find-API hits to a list of legacy memory shape dicts."""
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
    """Flatten find-API hits to a list of {memory, score} dicts."""
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
