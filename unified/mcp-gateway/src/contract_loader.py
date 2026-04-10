from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def load_contract(filename: str) -> dict[str, Any]:
    """Robustly load a contract JSON file from the contracts directory."""
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "contracts" / filename,
        base_dir.parent / "contracts" / filename,
        base_dir.parent.parent / "contracts" / filename,
    ]
    
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
            
    raise FileNotFoundError(
        f"Could not find {filename} in any of: {[str(c) for c in candidates]}"
    )
