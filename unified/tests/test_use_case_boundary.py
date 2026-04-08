from __future__ import annotations

from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v1_memory_uses_use_case_boundary_for_migrated_writes() -> None:
    source = _read(
        Path(__file__).resolve().parents[1] / "src" / "api" / "v1" / "memory.py"
    )

    assert "from ...use_cases.memory import (" in source
    assert "store_memories_many as handle_memory_write_many" in source
    assert "run_maintenance" in source
    assert "upsert_memories_bulk" in source

    forbidden = (
        "from ...memory_writes import (\n"
        "    handle_memory_write_many,\n"
        "    run_maintenance,\n"
        "    upsert_memories_bulk,\n"
        ")"
    )
    assert forbidden not in source


def test_v1_obsidian_uses_use_case_boundary_for_sync_writes() -> None:
    source = _read(
        Path(__file__).resolve().parents[1] / "src" / "api" / "v1" / "obsidian.py"
    )

    assert (
        "from ...use_cases.memory import store_memories_many as handle_memory_write_many"
        in source
    )
    assert "from ...memory_writes import handle_memory_write_many" not in source
