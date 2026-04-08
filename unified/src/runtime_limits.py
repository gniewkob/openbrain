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


def load_runtime_limits() -> dict[str, int]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "runtime_limits.json"
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)

    out: dict[str, int] = {}
    for key, default in _DEFAULTS.items():
        value = data.get(key, default)
        out[key] = int(value) if isinstance(value, (int, float)) else default
    return out

