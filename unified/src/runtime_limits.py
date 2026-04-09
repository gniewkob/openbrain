from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULTS = {
    "max_search_top_k": 100,
    "max_list_limit": 200,
    "max_sync_limit": 200,
    "max_bulk_items": 100,
}
def _validate_runtime_limits(data: Any) -> dict[str, int]:
    if not isinstance(data, dict):
        raise ValueError("runtime_limits must be a JSON object")
    out: dict[str, int] = {}
    for key in _DEFAULTS:
        value = data.get(key)
        if not isinstance(value, int):
            raise ValueError(f"runtime_limits.{key} must be an integer")
        if value <= 0:
            raise ValueError(f"runtime_limits.{key} must be > 0")
        out[key] = value
    return out


def load_runtime_limits() -> dict[str, int]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "runtime_limits.json"
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    return _validate_runtime_limits(data)
