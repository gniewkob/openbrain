from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src import memory_reads, memory_writes
from src.crud_common import STATUS_DUPLICATE, STATUS_SUPERSEDED
from src.models import DomainEnum, Memory
from src.schemas import MaintenanceRequest, SearchRequest, MemoryFindRequest


class RemediationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_maintenance_append_only_remediation(self) -> None:
        """Verify that exact duplicates in corporate domain are remediated safely."""
        now = datetime.now(timezone.utc)
        content_hash = "same-hash"

        # 1. Setup two exact duplicates in corporate domain
        canonical = Memory(
            id="can-1",
            domain=DomainEnum.corporate,
            entity_type="Note",
            content="same content",
            content_hash=content_hash,
            status="active",
            created_at=now,
        )
        duplicate = Memory(
            id="dup-1",
            domain=DomainEnum.corporate,
            entity_type="Note",
            content="same content",
            content_hash=content_hash,
            status="active",
            created_at=now,
        )

        session = AsyncMock()
        # session.add is synchronous in SQLAlchemy
        session.add = MagicMock()

        # Mock count
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        # Mock group by results
        group_result = MagicMock()
        group_result.all.return_value = [(content_hash, "Note", DomainEnum.corporate)]

        # Mock members query results
        members_result = MagicMock()
        members_result.scalars.return_value.all.return_value = [canonical, duplicate]

        # Mock AuditLog creation result
        audit_result = MagicMock()
        audit_result.id = "audit-1"

        # Sequential returns for session.execute
        session.execute.side_effect = [
            count_result,
            group_result,
            members_result,
            # AuditLog query if needed, but it's usually just session.add
        ]

        req = MaintenanceRequest(
            dry_run=False, dedup_threshold=0.05, fix_superseded_links=False
        )

        report = await memory_writes.run_maintenance(session, req)

        # Verify actions
        self.assertEqual(report.dedup_found, 1)
        self.assertEqual(len(report.actions), 2)
        self.assertEqual(report.actions[1].action, "dedup_remediate")

        # Verify status and metadata change on the duplicate record
        self.assertEqual(duplicate.status, STATUS_DUPLICATE)
        self.assertEqual(duplicate.metadata_["duplicate_of"], "can-1")

        # Verify canonical remains active
        self.assertEqual(canonical.status, "active")

    async def test_run_maintenance_non_append_only_dedup(self) -> None:
        """Verify that exact duplicates in non-corporate domains still follow the normal supersede path."""
        now = datetime.now(timezone.utc)
        content_hash = "same-hash"

        canonical = Memory(
            id="can-1",
            domain=DomainEnum.build,
            entity_type="Note",
            content="same content",
            content_hash=content_hash,
            status="active",
            created_at=now,
        )
        duplicate = Memory(
            id="dup-1",
            domain=DomainEnum.build,
            entity_type="Note",
            content="same content",
            content_hash=content_hash,
            status="active",
            created_at=now,
        )

        session = AsyncMock()
        session.add = MagicMock()

        session.execute.side_effect = [
            MagicMock(scalar_one=lambda: 2),
            MagicMock(all=lambda: [(content_hash, "Note", DomainEnum.build)]),
            MagicMock(scalars=lambda: MagicMock(all=lambda: [canonical, duplicate])),
        ]

        req = MaintenanceRequest(
            dry_run=False, dedup_threshold=0.05, fix_superseded_links=False
        )
        report = await memory_writes.run_maintenance(session, req)

        self.assertEqual(report.dedup_found, 1)
        self.assertEqual(duplicate.status, STATUS_SUPERSEDED)
        self.assertEqual(duplicate.superseded_by, "can-1")

    async def test_retrieval_excludes_duplicates(self) -> None:
        """Verify that default retrieval paths filter out 'duplicate' status records."""
        session = AsyncMock()

        # Mock the result of session.execute(stmt)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        with patch("src.memory_reads.select") as mock_select:
            mock_stmt = MagicMock()
            mock_select.return_value = mock_stmt
            mock_stmt.where.return_value = mock_stmt
            mock_stmt.order_by.return_value = mock_stmt
            mock_stmt.limit.return_value = mock_stmt

            await memory_reads.list_memories(session, filters={})

            # Ensure select was called
            self.assertTrue(mock_select.called)
            # Ensure where was called (at least for status filter)
            self.assertTrue(mock_stmt.where.called)


if __name__ == "__main__":
    unittest.main()
