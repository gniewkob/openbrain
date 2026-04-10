from __future__ import annotations

import json
import os
from typing import Any

from .contract_loader import load_contract

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
    try:
        data = load_contract("http_error_contracts.json")
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


def backend_request_failure_message(error: Exception) -> str:
    is_production = os.environ.get("ENV", "development").lower() == "production"
    if is_production:
        return "Backend request failed: upstream unavailable"
    return f"Backend request failed: {error}"
