from __future__ import annotations

from typing import Any


def normalize_find_hits_to_records(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        hit.get("record", hit) if isinstance(hit, dict) else hit
        for hit in hits
    ]


def normalize_find_hits_to_scored_memories(
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hits:
        if isinstance(hit, dict) and "record" in hit and "score" in hit:
            out.append({"memory": hit["record"], "score": hit["score"]})
        else:
            out.append(hit)
    return out

