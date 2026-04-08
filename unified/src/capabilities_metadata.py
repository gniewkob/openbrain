from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_capabilities_metadata() -> dict[str, Any]:
    contract_path = (
        Path(__file__).resolve().parents[1] / "contracts" / "capabilities_metadata.json"
    )
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    return {
        "api_version": data.get("api_version", "2.2.0"),
        "schema_changelog": data.get("schema_changelog", {}),
    }
