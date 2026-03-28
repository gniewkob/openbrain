from __future__ import annotations

import sys
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

# Make helpers importable from tests/ package
from pathlib import Path as _Path
import sys as _sys
_tests_dir = str(_Path(__file__).resolve().parent)
if _tests_dir not in _sys.path:
    _sys.path.insert(0, _tests_dir)
