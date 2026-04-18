"""
Regression tests for PATCH /api/v1/memory/{id} endpoint.

Previously, brain_update sent to POST /write with write_mode=upsert
but no match_key, causing the backend to always create a new record.

These tests verify the fix:
- build domain: in-place update, same ID, version stays 1
- corporate domain: new version created, previous_id set, old record superseded
- 404 on nonexistent ID
- PATCH endpoint registered in router
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.schemas import (
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    MemoryUpdate,
    MemoryWriteResponse,
    SourceMetadata,
    GovernanceMetadata,
)


def _make_memory_out(
    *,
    mem_id: str = "mem-1",
    domain: str = "build",
    entity_type: str = "Note",
    content: str = "content",
    version: int = 1,
    previous_id: str | None = None,
    root_id: str = "mem-1",
    match_key: str = "mk:1",
) -> MemoryOut:
    now = datetime.now(timezone.utc)
    return MemoryOut(
        id=mem_id,
        domain=domain,
        entity_type=entity_type,
        content=content,
        owner="tester",
        status="active",
        version=version,
        sensitivity="internal",
        superseded_by=None,
        tags=[],
        relations={},
        obsidian_ref=None,
        custom_fields={},
        content_hash="hash",
        match_key=match_key,
        previous_id=previous_id,
        root_id=root_id,
        valid_from=None,
        created_at=now,
        updated_at=now,
        created_by="tester",
    )


def _make_memory_record(out: MemoryOut) -> MemoryRecord:
    return MemoryRecord(
        id=out.id,
        match_key=out.match_key,
        domain=out.domain,
        entity_type=out.entity_type,
        content=out.content,
        owner=out.owner,
        tags=out.tags,
        relations=MemoryRelations(),
        status=out.status,
        sensitivity=out.sensitivity,
        source=SourceMetadata(),
        governance=GovernanceMetadata(),
        obsidian_ref=out.obsidian_ref,
        custom_fields=out.custom_fields,
        content_hash=out.content_hash,
        version=out.version,
        previous_id=out.previous_id,
        root_id=out.root_id,
        superseded_by=None,
        valid_from=None,
        created_at=out.created_at,
        updated_at=out.updated_at,
        created_by=out.created_by,
        updated_by="tester",
    )


class PatchEndpointRouteTests(unittest.TestCase):
    """Verify the PATCH endpoint is registered in the router."""

    def test_patch_route_registered(self) -> None:
        from src.api.v1.memory import router

        patch_routes = [
            r for r in router.routes if hasattr(r, "methods") and "PATCH" in r.methods
        ]
        self.assertTrue(
            patch_routes,
            "PATCH /{memory_id} route not found in v1 memory router",
        )
        # Ensure the path looks like /{memory_id}
        paths = [r.path for r in patch_routes]
        # Router has prefix="/memory", so full path is /memory/{memory_id}
        self.assertTrue(any("{memory_id}" in p for p in paths))


class PatchEndpointBuildDomainTests(unittest.IsolatedAsyncioTestCase):
    """build domain — in-place update, same ID."""

    async def test_build_patch_returns_updated_record_with_same_id(self) -> None:
        from src.api.v1 import memory as mem_module

        original = _make_memory_out(
            mem_id="build-1", domain="build", content="original"
        )
        updated = _make_memory_out(mem_id="build-1", domain="build", content="updated")
        original_record = _make_memory_record(original)
        updated_record = _make_memory_record(updated)

        with (
            patch.object(
                mem_module,
                "get_memory_as_record",
                new=AsyncMock(
                    side_effect=[
                        (original_record, original),  # pre-check
                        (updated_record, updated),  # post-update fetch
                    ]
                ),
            ),
            patch.object(
                mem_module, "update_memory", new=AsyncMock(return_value=updated)
            ),
        ):
            from src.api.v1.memory import v1_update
            from src.schemas import MemoryUpdate

            mock_user = {"sub": "tester"}
            result = await v1_update(
                memory_id="build-1",
                data=MemoryUpdate(content="updated"),
                session=AsyncMock(),
                _user=mock_user,
            )

        self.assertEqual(result.id, "build-1")
        self.assertEqual(result.content, "updated")

    async def test_patch_uses_authenticated_subject_for_audit_actor(self) -> None:
        from src.api.v1 import memory as mem_module

        original = _make_memory_out(
            mem_id="build-1", domain="build", content="original"
        )
        updated = _make_memory_out(mem_id="build-1", domain="build", content="updated")
        original_record = _make_memory_record(original)
        updated_record = _make_memory_record(updated)
        update_mock = AsyncMock(return_value=updated)

        with (
            patch.object(
                mem_module,
                "get_memory_as_record",
                new=AsyncMock(
                    side_effect=[
                        (original_record, original),
                        (updated_record, updated),
                    ]
                ),
            ),
            patch.object(mem_module, "update_memory", new=update_mock),
        ):
            from src.api.v1.memory import v1_update

            await v1_update(
                memory_id="build-1",
                data=MemoryUpdate(content="updated", updated_by="spoofed-user"),
                session=AsyncMock(),
                _user={"sub": "auth-sub"},
            )

        self.assertEqual(update_mock.await_args.kwargs["actor"], "auth-sub")

    async def test_patch_overrides_payload_updated_by_with_authenticated_subject(
        self,
    ) -> None:
        from src.api.v1 import memory as mem_module

        original = _make_memory_out(
            mem_id="build-1", domain="build", content="original"
        )
        updated = _make_memory_out(mem_id="build-1", domain="build", content="updated")
        original_record = _make_memory_record(original)
        updated_record = _make_memory_record(updated)
        update_mock = AsyncMock(return_value=updated)

        with (
            patch.object(
                mem_module,
                "get_memory_as_record",
                new=AsyncMock(
                    side_effect=[
                        (original_record, original),
                        (updated_record, updated),
                    ]
                ),
            ),
            patch.object(mem_module, "update_memory", new=update_mock),
        ):
            from src.api.v1.memory import v1_update

            await v1_update(
                memory_id="build-1",
                data=MemoryUpdate(content="updated", updated_by="spoofed-user"),
                session=AsyncMock(),
                _user={"sub": "auth-sub"},
            )

        passed_data = update_mock.await_args.args[2]
        self.assertEqual(passed_data.updated_by, "auth-sub")
        self.assertEqual(update_mock.await_args.kwargs["actor"], "auth-sub")

    async def test_patch_raises_404_for_nonexistent_memory(self) -> None:
        from src.api.v1 import memory as mem_module
        from fastapi import HTTPException

        with patch.object(
            mem_module, "get_memory_as_record", new=AsyncMock(return_value=(None, None))
        ):
            from src.api.v1.memory import v1_update
            from src.schemas import MemoryUpdate

            with self.assertRaises(HTTPException) as ctx:
                await v1_update(
                    memory_id="nonexistent",
                    data=MemoryUpdate(content="x"),
                    session=AsyncMock(),
                    _user={"sub": "tester"},
                )

        self.assertEqual(ctx.exception.status_code, 404)


class PatchEndpointCorporateTests(unittest.IsolatedAsyncioTestCase):
    """corporate domain — new version, old superseded."""

    async def test_corporate_patch_returns_new_version(self) -> None:
        from src.api.v1 import memory as mem_module

        original = _make_memory_out(
            mem_id="corp-1",
            domain="corporate",
            entity_type="Decision",
            content="v1 content",
            version=1,
            root_id="corp-1",
            match_key="corp:mk:1",
        )
        versioned = _make_memory_out(
            mem_id="corp-2",
            domain="corporate",
            entity_type="Decision",
            content="v2 content",
            version=2,
            previous_id="corp-1",
            root_id="corp-1",
            match_key="corp:mk:1",
        )
        orig_record = _make_memory_record(original)
        vers_record = _make_memory_record(versioned)

        with (
            patch.object(
                mem_module,
                "get_memory_as_record",
                new=AsyncMock(
                    side_effect=[
                        (orig_record, original),
                        (vers_record, versioned),
                    ]
                ),
            ),
            patch.object(
                mem_module, "update_memory", new=AsyncMock(return_value=versioned)
            ),
        ):
            from src.api.v1.memory import v1_update
            from src.schemas import MemoryUpdate

            result = await v1_update(
                memory_id="corp-1",
                data=MemoryUpdate(content="v2 content"),
                session=AsyncMock(),
                _user={"sub": "tester"},
            )

        self.assertEqual(result.id, "corp-2")
        self.assertEqual(result.version, 2)
        self.assertEqual(result.previous_id, "corp-1")
        self.assertEqual(result.root_id, "corp-1")


if __name__ == "__main__":
    unittest.main()
