"""
Obsidian CLI adapter - re-exports from common module for backward compatibility.

This module is kept for backward compatibility. New code should import from:
    from .common.obsidian_adapter import ObsidianCliAdapter, ObsidianNote, ...
"""

from __future__ import annotations

from .common.obsidian_adapter import (
    ObsidianCliAdapter,
    ObsidianCliError,
    ObsidianNote,
    note_to_memory_write_record,
    note_to_write_payload,
)

__all__ = [
    "ObsidianCliAdapter",
    "ObsidianCliError",
    "ObsidianNote",
    "note_to_memory_write_record",
    "note_to_write_payload",
]
