"""Tests for maintenance reports functionality."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import memory_reads
from src.models import AuditLog
from src.api.v1.memory import maintain_reports, maintain_report_detail


class MaintenanceReportsTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_maintenance_reports_maps_audit_entries(self) -> None:
        now = datetime.now(timezone.utc)
        audit_entry = AuditLog(
            id="audit-1",
            operation="maintain",
            tool_name="memory.maintain",
            memory_id=None,
            actor="tester",
            meta={
                "dry_run": True,
                "total_scanned": 192,
                "dedup_found": 9,
                "owners_normalized": 2,
                "links_fixed": 1,
                "actions": [{"action": "dedup", "memory_id": "mem-1", "detail": "Exact duplicate"}],
            },
            created_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [audit_entry]))

        reports = await memory_reads.list_maintenance_reports(session, limit=10)

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].report_id, "audit-1")
        self.assertEqual(reports[0].actor, "tester")
        self.assertTrue(reports[0].dry_run)
        self.assertEqual(reports[0].dedup_found, 9)
        self.assertEqual(reports[0].action_count, 1)

    async def test_main_endpoint_returns_report_entries(self) -> None:
        fake_entry = type("Entry", (), {
            "report_id": "audit-1",
            "created_at": datetime.now(timezone.utc),
            "actor": "tester",
            "dry_run": True,
            "total_scanned": 192,
            "dedup_found": 9,
            "owners_normalized": 2,
            "links_fixed": 1,
            "action_count": 4,
        })()

        with patch("src.api.v1.memory.list_maintenance_reports", new=AsyncMock(return_value=[fake_entry])):
            reports = await maintain_reports(limit=5, session=object(), _user={"sub": "tester"})

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].report_id, "audit-1")
        self.assertEqual(reports[0].action_count, 4)

    async def test_get_maintenance_report_returns_full_actions(self) -> None:
        now = datetime.now(timezone.utc)
        audit_entry = AuditLog(
            id="audit-1",
            operation="maintain",
            tool_name="memory.maintain",
            memory_id=None,
            actor="tester",
            meta={
                "dry_run": False,
                "total_scanned": 200,
                "dedup_found": 3,
                "owners_normalized": 1,
                "links_fixed": 2,
                "actions": [
                    {"action": "dedup", "memory_id": "mem-1", "detail": "Exact duplicate of mem-0"},
                    {"action": "fix_link", "memory_id": "mem-2", "detail": "Broken superseded_by"},
                ],
            },
            created_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: audit_entry)

        report = await memory_reads.get_maintenance_report(session, "audit-1")

        self.assertIsNotNone(report)
        self.assertEqual(report.report_id, "audit-1")
        self.assertFalse(report.dry_run)
        self.assertEqual(len(report.actions), 2)
        self.assertEqual(report.actions[0].action, "dedup")
        self.assertEqual(report.actions[1].memory_id, "mem-2")

    async def test_main_endpoint_returns_maintenance_report_detail(self) -> None:
        fake_detail = type("Detail", (), {
            "report_id": "audit-1",
            "created_at": datetime.now(timezone.utc),
            "actor": "tester",
            "dry_run": True,
            "actions": [type("Action", (), {"action": "dedup", "memory_id": "mem-1", "detail": "Exact duplicate"})()],
            "total_scanned": 192,
            "dedup_found": 9,
            "owners_normalized": 2,
            "links_fixed": 1,
        })()

        with patch("src.api.v1.memory.get_maintenance_report", new=AsyncMock(return_value=fake_detail)):
            report = await maintain_report_detail(report_id="audit-1", session=object(), _user={"sub": "tester"})

        self.assertEqual(report.report_id, "audit-1")
        self.assertEqual(len(report.actions), 1)
        self.assertEqual(report.actions[0].action, "dedup")


if __name__ == "__main__":
    unittest.main()
