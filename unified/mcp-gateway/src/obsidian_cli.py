"""
Obsidian CLI adapter - MCP Gateway compatibility layer.

This module imports from the shared common module to avoid code duplication.
The MCP gateway adds PYTHONPATH=../src to access shared modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add unified/src to path for shared imports
_src_path = Path(__file__).parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from common.obsidian_adapter import (  # noqa: E402
    ObsidianCliAdapter,
    ObsidianCliError,
    ObsidianNote,
    note_to_write_payload,
)

__all__ = [
    "ObsidianCliAdapter",
    "ObsidianCliError",
    "ObsidianNote", 
    "note_to_write_payload",
]
