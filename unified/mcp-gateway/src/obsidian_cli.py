from __future__ import annotations

import sys
from pathlib import Path


def _import_adapter():
    # Preferred path when package root already includes "src"
    try:
        from src.common.obsidian_adapter import (  # type: ignore[import-not-found]
            ObsidianCliAdapter,
            ObsidianCliError,
            ObsidianNote,
            note_to_write_payload,
        )

        return ObsidianCliAdapter, ObsidianCliError, ObsidianNote, note_to_write_payload
    except ModuleNotFoundError as exc:
        # Fallback only when the package layout doesn't expose `src`.
        if not (exc.name and exc.name.startswith("src")):
            raise

    # Fallback for gateway runtime: add unified/src to sys.path.
    unified_src = Path(__file__).resolve().parents[2] / "src"
    unified_src_s = str(unified_src)
    if unified_src.exists() and unified_src_s not in sys.path:
        sys.path.insert(0, unified_src_s)

    from common.obsidian_adapter import (  # type: ignore[import-not-found]
        ObsidianCliAdapter,
        ObsidianCliError,
        ObsidianNote,
        note_to_write_payload,
    )

    return ObsidianCliAdapter, ObsidianCliError, ObsidianNote, note_to_write_payload


ObsidianCliAdapter, ObsidianCliError, ObsidianNote, note_to_write_payload = _import_adapter()
__all__ = ["ObsidianCliAdapter", "ObsidianCliError", "ObsidianNote", "note_to_write_payload"]
