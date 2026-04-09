from __future__ import annotations

import sys
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

TESTS_DIR = str(Path(__file__).resolve().parent)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
