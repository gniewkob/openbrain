from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.schemas import (
    ExportRequest,
    MemoryCreate,
    MemoryFindRequest,
    MemoryOut,
    MemoryUpdate,
    MemoryWriteRecord,
    MemoryWriteRequest,
    SyncCheckRequest,
)
from src.security.policy import _effective_domain_scope

# Security functions live in src.security.policy — patch there
_POLICY = "src.security.policy"


def _memory_out(owner: str = "user-1", tenant_id: str | None = None) -> MemoryOut:
    return MemoryOut(
        id="mem-1",
        tenant_id=tenant_id,
        domain="build",
        entity_type="Note",
        content="payload",
        owner=owner,
        status="active",
        version=1,
        sensitivity="internal",
        superseded_by=None,
        tags=["alpha"],
        relations={},
        obsidian_ref=None,
        custom_fields={},
        content_hash="hash-1",
        match_key="mk-1",
        previous_id=None,
        root_id="mem-1",
        valid_from=None,
        created_at="2026-03-28T00:00:00Z",
        updated_at="2026-03-28T00:00:00Z",
        created_by="tester",
    )


class AccessControlTests(unittest.IsolatedAsyncioTestCase):
    """Access control tests using direct function calls with mocks."""

    async def test_v1_write_forces_owner_to_subject_for_scoped_user(self) -> None:
        from src.api.v1.memory import v1_write
        req = MemoryWriteRequest(record=MemoryWriteRecord(content="x", domain="build", entity_type="Note", owner=""))
        with patch("src.api.v1.memory.handle_memory_write", new=AsyncMock(return_value=type("R", (), {"status": "created"})())) as handle_memory_write, patch(
            f"{_POLICY}.PUBLIC_MODE", True
        ), patch(f"{_POLICY}.is_privileged_user", return_value=False), patch(f"{_POLICY}.get_subject", return_value="user-1"), patch(
            f"{_POLICY}._effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            await v1_write(req=req, session=object(), _user={"sub": "user-1"})

        passed = handle_memory_write.await_args.args[1]
        self.assertEqual(passed.record.owner, "user-1")

    async def test_effective_domain_scope_intersects_claims_and_registry(self) -> None:
        with patch(f"{_POLICY}.get_subject", return_value="user-1"), patch(f"{_POLICY}.get_tenant_id", return_value="tenant-a"), patch(
            f"{_POLICY}.get_domain_scope", return_value={"build", "corporate"}
        ), patch(f"{_POLICY}.get_registry_domain_scope", return_value={"build"}):
            scope = _effective_domain_scope({"sub": "user-1", "tenant_id": "tenant-a"}, "read")
        self.assertEqual(scope, {"build"})

    async def test_effective_domain_scope_uses_registry_when_claims_empty(self) -> None:
        with patch(f"{_POLICY}.get_subject", return_value="user-1"), patch(f"{_POLICY}.get_tenant_id", return_value="tenant-a"), patch(
            f"{_POLICY}.get_domain_scope", return_value=set()
        ), patch(f"{_POLICY}.get_registry_domain_scope", return_value={"personal"}):
            scope = _effective_domain_scope({"sub": "user-1", "tenant_id": "tenant-a"}, "read")
        self.assertEqual(scope, {"personal"})


if __name__ == "__main__":
    unittest.main()
