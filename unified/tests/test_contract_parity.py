"""Contract parity tests: gateway payload ↔ backend schema alignment.

Pure Pydantic unit tests — no DB, no HTTP, no mocks. Fast and deterministic.

For each gateway tool:
1. Build the exact payload the gateway sends.
2. Verify the backend schema accepts it without ValidationError.
3. Verify no required backend field is absent from the gateway payload.

These tests guard against schema drift where the gateway sends a payload
that the backend rejects (missing required fields or wrong types).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# brain_store → POST /api/v1/memory/write → MemoryWriteRequest
# ---------------------------------------------------------------------------


class TestBrainStoreContract:
    """Gateway payload for brain_store must be accepted by MemoryWriteRequest."""

    def _gateway_payload(self, **overrides) -> dict:
        """Exact payload brain_store sends (from gateway main.py:222-241)."""
        payload = {
            "record": {
                "content": "test content",
                "domain": "corporate",
                "entity_type": "Decision",
                "title": None,
                "sensitivity": "internal",
                "owner": "",
                "tenant_id": None,
                "tags": [],
                "custom_fields": {},
                "obsidian_ref": None,
                "match_key": None,
                "source": {"type": "agent", "system": "other"},
            },
            "write_mode": "upsert",
        }
        payload["record"].update(overrides)
        return payload

    def test_minimal_payload_accepted(self):
        """Minimal brain_store payload (all defaults) is accepted."""
        from src.schemas import MemoryWriteRequest

        MemoryWriteRequest.model_validate(self._gateway_payload())

    def test_full_payload_accepted(self):
        """Payload with all optional fields set is accepted."""
        from src.schemas import MemoryWriteRequest

        MemoryWriteRequest.model_validate(
            self._gateway_payload(
                title="A Decision",
                owner="user:alice",
                tenant_id="t-abc",
                tags=["engineering", "auth"],
                match_key="mk:store:test",
                obsidian_ref="Projects/my-note.md",
                custom_fields={"jira": "OB-123"},
            )
        )

    def test_domain_literal_build_accepted(self):
        from src.schemas import MemoryWriteRequest

        MemoryWriteRequest.model_validate(self._gateway_payload(domain="build"))

    def test_domain_literal_personal_accepted(self):
        from src.schemas import MemoryWriteRequest

        MemoryWriteRequest.model_validate(self._gateway_payload(domain="personal"))

    def test_missing_content_raises(self):
        """content is required — missing it must raise ValidationError."""
        from src.schemas import MemoryWriteRequest

        payload = self._gateway_payload()
        del payload["record"]["content"]
        with pytest.raises(ValidationError):
            MemoryWriteRequest.model_validate(payload)

    def test_missing_domain_raises(self):
        """domain is required — missing it must raise ValidationError."""
        from src.schemas import MemoryWriteRequest

        payload = self._gateway_payload()
        del payload["record"]["domain"]
        with pytest.raises(ValidationError):
            MemoryWriteRequest.model_validate(payload)


# ---------------------------------------------------------------------------
# brain_update → PATCH /api/v1/memory/{id} → MemoryUpdate
# ---------------------------------------------------------------------------


class TestBrainUpdateContract:
    """Gateway payload for brain_update must be accepted by MemoryUpdate."""

    def _gateway_payload(self, **overrides) -> dict:
        """Minimal payload brain_update sends (content + updated_by always)."""
        payload = {
            "content": "updated content",
            "updated_by": "agent",
        }
        payload.update(overrides)
        return payload

    def test_minimal_payload_accepted(self):
        from src.schemas import MemoryUpdate

        MemoryUpdate.model_validate(self._gateway_payload())

    def test_all_optional_fields_accepted(self):
        from src.schemas import MemoryUpdate

        MemoryUpdate.model_validate(
            self._gateway_payload(
                title="New Title",
                sensitivity="confidential",
                owner="user:bob",
                tenant_id="t-xyz",
                tags=["infra"],
                custom_fields={"key": "value"},
                obsidian_ref="Projects/note.md",
            )
        )

    def test_content_only_accepted(self):
        """Gateway always sends at least content + updated_by."""
        from src.schemas import MemoryUpdate

        MemoryUpdate.model_validate({"content": "new content", "updated_by": "agent"})

    def test_all_fields_optional_empty_dict_accepted(self):
        """MemoryUpdate allows empty dict (all fields optional)."""
        from src.schemas import MemoryUpdate

        MemoryUpdate.model_validate({})


# ---------------------------------------------------------------------------
# brain_upsert_bulk → POST /api/v1/memory/bulk-upsert → list[MemoryUpsertItem]
# ---------------------------------------------------------------------------


class TestBrainUpsertBulkContract:
    """Each item in brain_upsert_bulk payload must match MemoryUpsertItem."""

    def _item(self, **overrides) -> dict:
        """Typical item structure (gateway sends raw dicts from the caller)."""
        item = {
            "content": "bulk content",
            "domain": "corporate",
            "entity_type": "Decision",
            "sensitivity": "internal",
            "owner": "",
            "tags": [],
            "relations": {},
            "custom_fields": {},
        }
        item.update(overrides)
        return item

    def test_minimal_item_accepted(self):
        from src.schemas import MemoryUpsertItem

        MemoryUpsertItem.model_validate(self._item())

    def test_item_with_match_key_accepted(self):
        from src.schemas import MemoryUpsertItem

        MemoryUpsertItem.model_validate(self._item(match_key="mk:bulk:1"))

    def test_item_with_tenant_id_accepted(self):
        from src.schemas import MemoryUpsertItem

        MemoryUpsertItem.model_validate(self._item(tenant_id="t-tenant"))

    def test_missing_content_raises(self):
        from src.schemas import MemoryUpsertItem

        item = self._item()
        del item["content"]
        with pytest.raises(ValidationError):
            MemoryUpsertItem.model_validate(item)

    def test_list_of_items_all_valid(self):
        """Verify a list of items all pass — simulates the bulk endpoint."""
        from src.schemas import MemoryUpsertItem

        items = [
            self._item(content=f"record {i}", match_key=f"mk:{i}")
            for i in range(5)
        ]
        for item in items:
            MemoryUpsertItem.model_validate(item)


# ---------------------------------------------------------------------------
# brain_store_bulk → POST /api/v1/memory/write-many → MemoryWriteManyRequest
# ---------------------------------------------------------------------------


class TestBrainStoreBulkContract:
    """Gateway payload for brain_store_bulk must match MemoryWriteManyRequest."""

    def _gateway_payload(self, items: list[dict] | None = None) -> dict:
        """Exact payload brain_store_bulk sends (gateway main.py:699-703)."""
        records = items or [
            {
                "content": "record content",
                "domain": "corporate",
                "entity_type": "Decision",
                "sensitivity": "internal",
                "owner": "",
                "tags": [],
                "relations": {},
                "custom_fields": {},
            }
        ]
        return {"records": records, "write_mode": "upsert"}

    def test_minimal_payload_accepted(self):
        from src.schemas import MemoryWriteManyRequest

        MemoryWriteManyRequest.model_validate(self._gateway_payload())

    def test_multiple_records_accepted(self):
        from src.schemas import MemoryWriteManyRequest

        payload = self._gateway_payload(
            items=[
                {
                    "content": f"record {i}",
                    "domain": "build",
                    "entity_type": "Note",
                    "sensitivity": "internal",
                    "owner": "",
                    "tags": [],
                    "relations": {},
                    "custom_fields": {},
                }
                for i in range(3)
            ]
        )
        MemoryWriteManyRequest.model_validate(payload)


# ---------------------------------------------------------------------------
# brain_sync_check → POST /api/v1/memory/sync-check → SyncCheckRequest
# ---------------------------------------------------------------------------


class TestBrainSyncCheckContract:
    """Gateway payload for brain_sync_check must match SyncCheckRequest."""

    def test_with_memory_id_only_accepted(self):
        from src.schemas import SyncCheckRequest

        SyncCheckRequest.model_validate(
            {"memory_id": "mem-abc", "match_key": None, "obsidian_ref": None}
        )

    def test_with_match_key_only_accepted(self):
        from src.schemas import SyncCheckRequest

        SyncCheckRequest.model_validate(
            {"memory_id": None, "match_key": "mk:note:1", "obsidian_ref": None}
        )

    def test_with_obsidian_ref_only_accepted(self):
        from src.schemas import SyncCheckRequest

        SyncCheckRequest.model_validate(
            {
                "memory_id": None,
                "match_key": None,
                "obsidian_ref": "Projects/note.md",
            }
        )

    def test_with_file_hash_accepted(self):
        from src.schemas import SyncCheckRequest

        SyncCheckRequest.model_validate(
            {
                "memory_id": "mem-abc",
                "match_key": None,
                "obsidian_ref": None,
                "file_hash": "sha256:abc123",
            }
        )

    def test_gateway_sends_all_four_fields(self):
        """brain_sync_check always sends all 4 fields (may be None).
        Backend must accept this without error."""
        from src.schemas import SyncCheckRequest

        # Gateway always passes all four keys (main.py:470-478)
        payload = {
            "memory_id": "mem-1",
            "match_key": None,
            "obsidian_ref": None,
            "file_hash": None,
        }
        SyncCheckRequest.model_validate(payload)

    def test_zero_identifiers_rejected(self):
        """Providing no identifier must raise ValidationError."""
        from src.schemas import SyncCheckRequest

        with pytest.raises(ValidationError):
            SyncCheckRequest.model_validate(
                {"memory_id": None, "match_key": None, "obsidian_ref": None}
            )

    def test_two_identifiers_rejected(self):
        """Providing two identifiers must raise ValidationError."""
        from src.schemas import SyncCheckRequest

        with pytest.raises(ValidationError):
            SyncCheckRequest.model_validate(
                {
                    "memory_id": "mem-1",
                    "match_key": "mk:1",
                    "obsidian_ref": None,
                    "file_hash": None,
                }
            )
