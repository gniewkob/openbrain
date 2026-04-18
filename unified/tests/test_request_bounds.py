from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.schemas import (
    ExportRequest,
    MemoryCreate,
    MemoryGetContextRequest,
    ObsidianSyncRequest,
    SearchRequest,
)


class RequestBoundsTests(unittest.TestCase):
    def test_search_request_rejects_excessive_top_k(self) -> None:
        with self.assertRaises(ValidationError):
            SearchRequest(query="policy", top_k=999)

    def test_get_context_rejects_excessive_max_items(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryGetContextRequest(query="policy", max_items=999)

    def test_memory_create_rejects_excessive_content(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryCreate(content="x" * 20001, domain="build", entity_type="Note")

    def test_obsidian_sync_rejects_excessive_limit(self) -> None:
        with self.assertRaises(ValidationError):
            ObsidianSyncRequest(limit=999)

    def test_export_rejects_excessive_id_count(self) -> None:
        with self.assertRaises(ValidationError):
            ExportRequest(ids=["mem-1"] * 101)


if __name__ == "__main__":
    unittest.main()
