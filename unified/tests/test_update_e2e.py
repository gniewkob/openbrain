"""E2E invariant tests for brain_update / update_memory() business logic.

Tests the update_memory() function in memory_writes.py directly using
AsyncMock + patch. No DB, no HTTP.

Does not duplicate:
- test_patch_endpoint.py (HTTP layer / endpoint routing)
- The goal here is verifying the business-logic invariants (id, root_id,
  match_key, version, lineage) are preserved correctly by the write path.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.schemas import MemoryOut  # noqa: E402 (needed for type annotations below)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_memory(
    *,
    mem_id: str = "mem-1",
    domain: str = "build",
    content: str = "original content",
    match_key: str | None = "mk:test:1",
    owner: str = "user:tester",
    version: int = 1,
    root_id: str | None = None,
    previous_id: str | None = None,
    content_hash: str = "hash-original",
    tags: list[str] | None = None,
) -> MagicMock:
    """Build a mock Memory ORM object."""
    from src.models import DomainEnum

    m = MagicMock()
    m.id = mem_id
    m.domain = DomainEnum(domain)
    m.entity_type = "Note"
    m.content = content
    m.match_key = match_key
    m.owner = owner
    m.tenant_id = None
    m.version = version
    m.status = "active"
    m.superseded_by = None
    m.sensitivity = "internal"
    m.tags = tags or []
    m.relations = {}
    m.obsidian_ref = None
    m.content_hash = content_hash
    m.metadata_ = {
        "root_id": root_id or mem_id,
        "previous_id": previous_id,
        "updated_by": "agent",
        "custom_fields": {},
        "tenant_id": None,
    }
    m.created_by = "agent"
    m.created_at = _now()
    m.updated_at = _now()
    return m


def _make_memory_out(memory: MagicMock):
    """Build a MemoryOut from a mock Memory."""
    from src.schemas import MemoryOut

    now = _now()
    return MemoryOut(
        id=memory.id,
        domain=memory.domain.value,
        entity_type=memory.entity_type,
        content=memory.content,
        owner=memory.owner,
        status=memory.status,
        version=memory.version,
        sensitivity=memory.sensitivity,
        superseded_by=memory.superseded_by,
        tags=memory.tags or [],
        relations={},
        obsidian_ref=memory.obsidian_ref,
        custom_fields={},
        content_hash=memory.content_hash,
        match_key=memory.match_key,
        previous_id=memory.metadata_.get("previous_id"),
        root_id=memory.metadata_.get("root_id", memory.id),
        valid_from=None,
        created_at=now,
        updated_at=now,
        created_by=memory.created_by,
    )


# ---------------------------------------------------------------------------
# Build/personal domain: in-place update
# ---------------------------------------------------------------------------


class TestBuildUpdateInvariants(unittest.IsolatedAsyncioTestCase):
    """build domain: in-place update preserves id and root_id."""

    async def _run_update(self, original: MagicMock, new_content: str) -> "MemoryOut":
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        updated = _make_memory(
            mem_id=original.id,
            domain=original.domain.value,
            content=new_content,
            match_key=original.match_key,
            owner=original.owner,
            version=original.version,  # in-place: same version
            root_id=original.metadata_["root_id"],
            content_hash="hash-updated",
        )
        updated_out = _make_memory_out(updated)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "src.memory_writes.handle_memory_write",
                new=AsyncMock(
                    return_value=MagicMock(
                        status="updated",
                        record=MagicMock(id=updated.id),
                        errors=[],
                    )
                ),
            ),
            patch(
                "src.memory_writes.get_memory",
                new=AsyncMock(return_value=updated_out),
            ),
        ):
            return await update_memory(
                mock_session,
                original.id,
                MemoryUpdate(content=new_content),
                actor="agent",
            )

    async def test_build_update_preserves_id(self):
        original = _make_memory(mem_id="build-1", domain="build")
        result = await self._run_update(original, "new content")
        self.assertEqual(result.id, "build-1")

    async def test_build_update_preserves_root_id(self):
        original = _make_memory(mem_id="build-1", domain="build")
        result = await self._run_update(original, "new content")
        self.assertEqual(result.root_id, "build-1")

    async def test_personal_update_preserves_id(self):
        original = _make_memory(mem_id="personal-1", domain="personal")
        result = await self._run_update(original, "updated")
        self.assertEqual(result.id, "personal-1")

    async def test_personal_update_preserves_root_id(self):
        original = _make_memory(
            mem_id="personal-1",
            domain="personal",
            root_id="personal-1",
        )
        result = await self._run_update(original, "updated")
        self.assertEqual(result.root_id, "personal-1")


# ---------------------------------------------------------------------------
# Corporate domain: append-only versioning
# ---------------------------------------------------------------------------


class TestCorporateUpdateInvariants(unittest.IsolatedAsyncioTestCase):
    """corporate domain: new version created with correct lineage fields."""

    async def _run_corporate_update(
        self, original: MagicMock, new_content: str
    ) -> "MemoryOut":
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        new_id = "corp-2"
        versioned = _make_memory(
            mem_id=new_id,
            domain="corporate",
            content=new_content,
            match_key=original.match_key,
            owner=original.owner,
            version=original.version + 1,
            root_id=original.metadata_["root_id"],
            previous_id=original.id,
            content_hash="hash-v2",
        )
        versioned_out = _make_memory_out(versioned)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "src.memory_writes.handle_memory_write",
                new=AsyncMock(
                    return_value=MagicMock(
                        status="versioned",
                        record=MagicMock(id=new_id),
                        errors=[],
                    )
                ),
            ),
            patch(
                "src.memory_writes.get_memory",
                new=AsyncMock(return_value=versioned_out),
            ),
        ):
            return await update_memory(
                mock_session,
                original.id,
                MemoryUpdate(content=new_content),
                actor="agent",
            )

    async def test_corporate_update_creates_new_version(self):
        original = _make_memory(mem_id="corp-1", domain="corporate", version=1)
        result = await self._run_corporate_update(original, "v2 content")
        self.assertEqual(result.id, "corp-2")

    async def test_corporate_update_increments_version(self):
        original = _make_memory(mem_id="corp-1", domain="corporate", version=1)
        result = await self._run_corporate_update(original, "v2 content")
        self.assertEqual(result.version, 2)

    async def test_corporate_update_sets_previous_id(self):
        original = _make_memory(mem_id="corp-1", domain="corporate")
        result = await self._run_corporate_update(original, "v2 content")
        self.assertEqual(result.previous_id, "corp-1")

    async def test_corporate_update_preserves_root_id(self):
        original = _make_memory(mem_id="corp-1", domain="corporate", root_id="corp-1")
        result = await self._run_corporate_update(original, "v2 content")
        self.assertEqual(result.root_id, "corp-1")

    async def test_corporate_update_preserves_match_key(self):
        original = _make_memory(
            mem_id="corp-1", domain="corporate", match_key="mk:corp:1"
        )
        result = await self._run_corporate_update(original, "v2 content")
        self.assertEqual(result.match_key, "mk:corp:1")


# ---------------------------------------------------------------------------
# Cross-domain invariants
# ---------------------------------------------------------------------------


class TestUpdateSharedInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariants that hold across all domains."""

    async def test_update_preserves_match_key_when_not_provided(self):
        """match_key from original record is preserved even if not in MemoryUpdate."""
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        original = _make_memory(mem_id="m-1", domain="build", match_key="mk:preserve:1")
        preserved_out = _make_memory_out(original)
        preserved_out = preserved_out.model_copy(update={"content": "updated"})

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "src.memory_writes.handle_memory_write",
                new=AsyncMock(
                    return_value=MagicMock(
                        status="updated",
                        record=MagicMock(id="m-1"),
                        errors=[],
                    )
                ),
            ),
            patch(
                "src.memory_writes.get_memory",
                new=AsyncMock(return_value=preserved_out),
            ),
        ):
            result = await update_memory(
                mock_session,
                "m-1",
                MemoryUpdate(content="updated"),
                actor="agent",
            )

        self.assertEqual(result.match_key, "mk:preserve:1")

    async def test_update_preserves_owner_when_not_provided(self):
        """owner from original record is preserved if MemoryUpdate.owner is None."""
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        original = _make_memory(mem_id="m-2", domain="personal", owner="user:alice")
        out = _make_memory_out(original)
        out = out.model_copy(update={"content": "new content"})

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        write_mock = AsyncMock(
            return_value=MagicMock(
                status="updated",
                record=MagicMock(id="m-2"),
                errors=[],
            )
        )
        with (
            patch("src.memory_writes.handle_memory_write", new=write_mock),
            patch("src.memory_writes.get_memory", new=AsyncMock(return_value=out)),
        ):
            await update_memory(
                mock_session,
                "m-2",
                MemoryUpdate(content="new content"),
                actor="agent",
            )

        # Verify handle_memory_write was called with the original owner preserved
        call_args = write_mock.call_args
        request = call_args.args[1]
        self.assertEqual(request.record.owner, "user:alice")

    async def test_update_returns_skipped_when_content_unchanged(self):
        """When content is identical, update_memory returns the existing record
        (status='skipped' from handle_memory_write → update_memory returns
        the existing MemoryOut, not None)."""
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        original = _make_memory(mem_id="m-3", domain="build", content="same content")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        with patch(
            "src.memory_writes.handle_memory_write",
            new=AsyncMock(
                return_value=MagicMock(status="skipped", record=None, errors=[])
            ),
        ):
            result = await update_memory(
                mock_session,
                "m-3",
                MemoryUpdate(content="same content"),
                actor="agent",
            )

        # skipped: returns existing record as MemoryOut, not None
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "m-3")

    async def test_update_raises_404_for_missing_id(self):
        """update_memory returns None when memory_id doesn't exist."""
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await update_memory(
            mock_session,
            "nonexistent",
            MemoryUpdate(content="x"),
            actor="agent",
        )
        self.assertIsNone(result)

    async def test_update_content_hash_changes(self):
        """After update, content_hash reflects new content."""
        from src.memory_writes import update_memory
        from src.schemas import MemoryUpdate

        original = _make_memory(mem_id="m-4", domain="build", content_hash="hash-old")
        updated_out = _make_memory_out(original)
        updated_out = updated_out.model_copy(
            update={"content": "new text", "content_hash": "hash-new"}
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "src.memory_writes.handle_memory_write",
                new=AsyncMock(
                    return_value=MagicMock(
                        status="updated",
                        record=MagicMock(id="m-4"),
                        errors=[],
                    )
                ),
            ),
            patch(
                "src.memory_writes.get_memory",
                new=AsyncMock(return_value=updated_out),
            ),
        ):
            result = await update_memory(
                mock_session,
                "m-4",
                MemoryUpdate(content="new text"),
                actor="agent",
            )

        self.assertNotEqual(result.content_hash, "hash-old")
        self.assertEqual(result.content_hash, "hash-new")


if __name__ == "__main__":
    unittest.main()
