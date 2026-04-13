"""Tests for update_memory and upsert_memories_bulk extracted helpers."""

from __future__ import annotations
import pytest
from unittest.mock import MagicMock


class TestBuildUpdateWriteRecord:
    def test_uses_data_content_when_provided(self):
        from src.memory_writes import _build_update_write_record
        from src.schemas import MemoryUpdate

        memory = MagicMock()
        memory.match_key = "k1"
        memory.content = "old"
        memory.domain = MagicMock(value="build")
        memory.entity_type = "Note"
        memory.metadata_ = {}
        memory.owner = "alice"
        memory.tenant_id = None
        memory.tags = []
        memory.relations = {}
        memory.obsidian_ref = None
        memory.sensitivity = "internal"
        data = MemoryUpdate(content="new_content")
        record = _build_update_write_record(memory, data)
        assert record.content == "new_content"

    def test_falls_back_to_memory_content_when_data_is_none(self):
        from src.memory_writes import _build_update_write_record
        from src.schemas import MemoryUpdate

        memory = MagicMock()
        memory.match_key = "k1"
        memory.content = "original"
        memory.domain = MagicMock(value="build")
        memory.entity_type = "Note"
        memory.metadata_ = {}
        memory.owner = "alice"
        memory.tenant_id = None
        memory.tags = []
        memory.relations = {}
        memory.obsidian_ref = None
        memory.sensitivity = "internal"
        data = MemoryUpdate()
        record = _build_update_write_record(memory, data)
        assert record.content == "original"


class TestClassifyBulkResults:
    def test_created_goes_to_inserted(self):
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        result = BatchResultItem(input_index=0, record_id="id1", status="created")
        mem = MagicMock()
        inserted, updated, skipped = _classify_bulk_results([result], {"id1": mem})
        assert mem in inserted
        assert updated == []
        assert skipped == []

    def test_updated_goes_to_updated(self):
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        result = BatchResultItem(input_index=0, record_id="id1", status="updated")
        mem = MagicMock()
        inserted, updated, skipped = _classify_bulk_results([result], {"id1": mem})
        assert mem in updated

    def test_skipped_goes_to_skipped_list(self):
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        result = BatchResultItem(input_index=0, record_id="id1", status="skipped")
        inserted, updated, skipped = _classify_bulk_results([result], {})
        assert "id1" in skipped
