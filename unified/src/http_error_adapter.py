from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULTS = {
    "status_labels": {
        "401": "Authentication required",
        "403": "Access denied",
        "404": "Resource not found",
        "422": "Validation error",
    },
    "fallback_5xx": "Internal server error",
    "fallback_other": "Request failed",
}


def _load_contract() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1] / "contracts" / "http_error_contracts.json"
    )
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)
    merged = dict(_DEFAULTS)
    merged.update({k: data.get(k, v) for k, v in _DEFAULTS.items()})
    return merged


_CONTRACT = _load_contract()


def backend_error_message(status_code: int, detail: Any) -> str:
    is_production = os.environ.get("ENV", "development").lower() == "production"
    if is_production:
        labels = _CONTRACT["status_labels"]
        label = labels.get(
            str(status_code),
            _CONTRACT["fallback_5xx"] if status_code >= 500 else _CONTRACT["fallback_other"],
        )
        return f"Backend {status_code}: {label}"

    if isinstance(detail, (dict, list)):
        detail_text = json.dumps(detail, ensure_ascii=False)
    else:
        detail_text = str(detail)
    return f"Backend {status_code}: {detail_text}"

