from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from tests.test_metrics import _import_main_with_fake_auth_deps
from src.schemas import ExportRequest, MemoryCreate, MemoryFindRequest, MemoryOut, MemoryUpdate, MemoryWriteRecord, MemoryWriteRequest, SyncCheckRequest


main = _import_main_with_fake_auth_deps()


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
        created_at="2026-03-28T00:00:00Z",  # pydantic will parse
        updated_at="2026-03-28T00:00:00Z",
        created_by="tester",
    )


class AccessControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_memory_forces_owner_to_subject_for_scoped_user(self) -> None:
        data = MemoryCreate(content="x", domain="build", entity_type="Note", owner="")
        with patch.object(main, "store_memory", new=AsyncMock(return_value=_memory_out(owner="user-1"))) as store_memory, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_subject", return_value="user-1"), patch.object(
            main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            await main.create_memory(data=data, session=object(), _user={"sub": "user-1"})

        passed = store_memory.await_args.args[1]
        self.assertEqual(passed.owner, "user-1")
        self.assertEqual(store_memory.await_args.kwargs["actor"], "user-1")

    async def test_v1_write_forces_owner_to_subject_for_scoped_user(self) -> None:
        req = MemoryWriteRequest(record=MemoryWriteRecord(content="x", domain="build", entity_type="Note", owner=""))
        with patch.object(main, "handle_memory_write", new=AsyncMock(return_value=type("R", (), {"status": "created"})())) as handle_memory_write, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_subject", return_value="user-1"), patch.object(
            main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            await main.v1_write(req=req, session=object(), _user={"sub": "user-1"})

        passed = handle_memory_write.await_args.args[1]
        self.assertEqual(passed.record.owner, "user-1")

    async def test_create_memory_forces_tenant_to_claim_for_scoped_tenant_user(self) -> None:
        data = MemoryCreate(content="x", domain="build", entity_type="Note", owner="", tenant_id=None)
        with patch.object(main, "store_memory", new=AsyncMock(return_value=_memory_out(tenant_id="tenant-a"))) as store_memory, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_tenant_id", return_value="tenant-a"), patch.object(
            main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            await main.create_memory(data=data, session=object(), _user={"sub": "user-1", "tenant_id": "tenant-a"})

        passed = store_memory.await_args.args[1]
        self.assertEqual(passed.tenant_id, "tenant-a")
        self.assertEqual(store_memory.await_args.kwargs["actor"], "user-1")

    async def test_search_applies_tenant_scope_when_claim_present(self) -> None:
        req = main.SearchRequest(query="x", top_k=5, filters={"owner": "someone-else"})
        with patch.object(main, "search_memories", new=AsyncMock(return_value=[])) as search_memories, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_tenant_id", return_value="tenant-a"):
            await main.search(req=req, session=object(), _user={"sub": "user-1", "tenant_id": "tenant-a"})

        passed_req = search_memories.await_args.args[1]
        self.assertEqual(passed_req.filters["tenant_id"], "tenant-a")
        self.assertNotIn("owner", passed_req.filters)

    async def test_create_memory_blocks_write_to_disallowed_domain(self) -> None:
        data = MemoryCreate(content="x", domain="corporate", entity_type="Note", owner="")
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "get_domain_scope", return_value={"build"}):
            with self.assertRaises(HTTPException) as ctx:
                await main.create_memory(data=data, session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_read_memories_applies_owner_scope_for_scoped_user(self) -> None:
        with patch.object(main, "list_memories", new=AsyncMock(return_value=[])) as list_memories, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_subject", return_value="user-1"):
            await main.read_memories(domain="build", limit=10, session=object(), _user={"sub": "user-1"})

        filters = list_memories.await_args.args[1]
        self.assertEqual(filters["owner"], "user-1")
        self.assertEqual(filters["domain"], "build")

    async def test_read_memories_blocks_requested_domain_outside_policy(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False), patch.object(
            main, "get_subject", return_value="user-1"
        ), patch.object(main, "_effective_domain_scope", return_value={"build"}):
            with self.assertRaises(HTTPException) as ctx:
                await main.read_memories(domain="corporate", limit=10, session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_effective_domain_scope_intersects_claims_and_registry(self) -> None:
        with patch.object(main, "get_subject", return_value="user-1"), patch.object(main, "get_tenant_id", return_value="tenant-a"), patch.object(
            main, "get_domain_scope", return_value={"build", "corporate"}
        ), patch.object(main, "get_registry_domain_scope", return_value={"build"}):
            scope = main._effective_domain_scope({"sub": "user-1", "tenant_id": "tenant-a"}, "read")
        self.assertEqual(scope, {"build"})

    async def test_effective_domain_scope_uses_registry_when_claims_empty(self) -> None:
        with patch.object(main, "get_subject", return_value="user-1"), patch.object(main, "get_tenant_id", return_value="tenant-a"), patch.object(
            main, "get_domain_scope", return_value=set()
        ), patch.object(main, "get_registry_domain_scope", return_value={"personal"}):
            scope = main._effective_domain_scope({"sub": "user-1", "tenant_id": "tenant-a"}, "read")
        self.assertEqual(scope, {"personal"})

    async def test_search_applies_owner_scope_for_scoped_user(self) -> None:
        req = main.SearchRequest(query="x", top_k=5, filters={})
        with patch.object(main, "search_memories", new=AsyncMock(return_value=[])) as search_memories, patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_subject", return_value="user-1"), patch.object(main, "get_tenant_id", return_value=""):
            await main.search(req=req, session=object(), _user={"sub": "user-1"})

        passed_req = search_memories.await_args.args[1]
        self.assertEqual(passed_req.filters["owner"], "user-1")

    async def test_update_blocks_access_to_other_tenant_for_scoped_user(self) -> None:
        with patch.object(main, "get_memory", new=AsyncMock(return_value=_memory_out(owner="user-1", tenant_id="tenant-b"))), patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_tenant_id", return_value="tenant-a"), patch.object(
            main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.update(
                    memory_id="mem-1",
                    data=MemoryUpdate(content="x", tenant_id="tenant-a"),
                    session=object(),
                    _user={"sub": "user-1", "tenant_id": "tenant-a"},
                )
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_update_blocks_access_to_other_owner_for_scoped_user(self) -> None:
        with patch.object(main, "get_memory", new=AsyncMock(return_value=_memory_out(owner="other-user"))), patch.object(
            main, "PUBLIC_MODE", True
        ), patch.object(main, "is_privileged_user", return_value=False), patch.object(main, "get_subject", return_value="user-1"), patch.object(
            main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.update(memory_id="mem-1", data=MemoryUpdate(content="x"), session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_update_uses_authenticated_subject_as_actor(self) -> None:
        with patch.object(main, "get_memory", new=AsyncMock(return_value=_memory_out(owner="user-1"))), patch.object(
            main, "update_memory", new=AsyncMock(return_value=_memory_out(owner="user-1"))
        ) as update_memory, patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False), patch.object(
            main, "get_subject", return_value="user-1"
        ), patch.object(main, "_effective_domain_scope", return_value={"build", "corporate", "personal"}):
            await main.update(
                memory_id="mem-1",
                data=MemoryUpdate(content="x", updated_by="spoofed-user"),
                session=object(),
                _user={"sub": "user-1"},
            )

        self.assertEqual(update_memory.await_args.kwargs["actor"], "user-1")

    async def test_delete_requires_admin(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                await main.delete(memory_id="mem-1", session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_delete_honors_admin_domain_scope(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=True), patch.object(
            main, "get_memory", new=AsyncMock(return_value=_memory_out(owner="user-1", tenant_id="tenant-a",))
        ), patch.object(main, "get_domain_scope", return_value={"corporate"}):
            with self.assertRaises(HTTPException) as ctx:
                await main.delete(memory_id="mem-1", session=object(), _user={"sub": "admin-user"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_maintain_requires_admin(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                await main.maintain(req=object(), session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_export_requires_admin(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                await main.export(req=ExportRequest(ids=["mem-1"]), session=object(), _user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_export_hides_records_outside_admin_domain_scope(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=True), patch.object(
            main, "get_memory", new=AsyncMock(return_value=_memory_out())
        ), patch.object(main, "get_domain_scope", return_value={"corporate"}):
            with self.assertRaises(HTTPException) as ctx:
                await main.export(req=ExportRequest(ids=["mem-1"]), session=object(), _user={"sub": "admin-user"})
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_sync_check_hides_records_outside_admin_domain_scope(self) -> None:
        sync_result = {
            "status": "exists",
            "message": "Memory exists.",
            "memory_id": "mem-1",
            "match_key": "mk-1",
            "obsidian_ref": None,
            "stored_hash": "hash-1",
            "provided_hash": None,
        }
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=True), patch.object(
            main, "sync_check", new=AsyncMock(return_value=sync_result)
        ), patch.object(main, "get_memory", new=AsyncMock(return_value=_memory_out())), patch.object(
            main, "get_domain_scope", return_value={"corporate"}
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.check_sync_endpoint(
                    req=SyncCheckRequest(match_key="mk-1"),
                    session=object(),
                    _user={"sub": "admin-user"},
                )
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
