from __future__ import annotations

from src.memory_paths import (
    memory_absolute_path,
    memory_item_absolute_path,
    memory_item_path,
    memory_path,
)


def test_memory_paths_contract_values() -> None:
    assert memory_path("find") == "/find"
    assert memory_path("write_many") == "/write-many"
    assert memory_absolute_path("find") == "/api/v1/memory/find"


def test_memory_item_paths() -> None:
    assert memory_item_path("mem-1") == "/mem-1"
    assert memory_item_absolute_path("mem-1") == "/api/v1/memory/mem-1"

