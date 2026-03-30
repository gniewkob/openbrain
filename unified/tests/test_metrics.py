from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src.telemetry import reset_metrics
from src.schemas import MaintenanceAction, MemoryWriteRecord, MemoryWriteRequest


def _import_main_with_fake_auth_deps():
    fake_jose = types.ModuleType("jose")
    fake_jose.jwt = types.SimpleNamespace(decode=lambda *args, **kwargs: {})
    fake_jwt = types.ModuleType("jwt")

    class FakePyJWKClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_signing_key_from_jwt(self, token):
            return types.SimpleNamespace(key="fake-key")

    fake_jwt.PyJWKClient = FakePyJWKClient

    existing_jose = sys.modules.get("jose")
    existing_jwt = sys.modules.get("jwt")
    sys.modules["jose"] = fake_jose
    sys.modules["jwt"] = fake_jwt
    try:
        from src import main
        return main
    finally:
        if existing_jose is not None:
            sys.modules["jose"] = existing_jose
        else:
            sys.modules.pop("jose", None)
        if existing_jwt is not None:
            sys.modules["jwt"] = existing_jwt
        else:
            sys.modules.pop("jwt", None)


main = _import_main_with_fake_auth_deps()


class MetricsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_metrics()

    async def test_v1_write_counts_versioned_operation(self) -> None:
        fake_result = type("R", (), {"status": "versioned"})()
        with patch.object(main, "handle_memory_write", new=AsyncMock(return_value=fake_result)):
            result = await main.v1_write(
                req=MemoryWriteRequest(record=MemoryWriteRecord(content="x", domain="build", entity_type="Note")),
                session=object(),
                _user={"sub": "tester"},
            )

        self.assertEqual(result.status, "versioned")
        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 0,
            "superseded": 0,
            "archived": 0,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})
        self.assertEqual(snapshot["counters"]["memories_versioned_total"], 1)

    async def test_sync_check_counts_exists_status(self) -> None:
        with patch.object(main, "sync_check", new=AsyncMock(return_value={
            "status": "exists",
            "message": "Memory exists.",
            "memory_id": "mem-1",
            "match_key": "mk-1",
            "obsidian_ref": None,
            "stored_hash": "abc",
            "provided_hash": None,
        })), patch.object(main, "get_memory", new=AsyncMock(return_value=main.MemoryOut(
            id="mem-1",
            tenant_id=None,
            domain="build",
            entity_type="Note",
            content="payload",
            owner="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            obsidian_ref=None,
            custom_fields={},
            content_hash="abc",
            match_key="mk-1",
            previous_id=None,
            root_id="mem-1",
            valid_from=None,
            created_at="2026-03-28T00:00:00Z",
            updated_at="2026-03-28T00:00:00Z",
            created_by="tester",
        ))):
            response = await main.check_sync_endpoint(
                req=main.SyncCheckRequest(match_key="mk-1"),
                memory_id=None,
                match_key=None,
                obsidian_ref=None,
                file_hash=None,
                session=object(),
                _user={"sub": "tester"},
            )

        self.assertEqual(response.status, "exists")
        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 0,
            "superseded": 0,
            "archived": 0,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})
        self.assertEqual(snapshot["counters"]["sync_checks_total"], 1)
        self.assertEqual(snapshot["counters"]["sync_exists_total"], 1)

    async def test_maintain_counts_hygiene_metrics(self) -> None:
        fake_report = type("Report", (), {
            "report_id": "audit-1",
            "actions": [
                MaintenanceAction(action="policy_skip", memory_id="mem-1", detail="Skipped dedup mutation for append-only memory"),
                MaintenanceAction(action="policy_skip", memory_id="mem-2", detail="Skipped owner normalization for append-only memory"),
                MaintenanceAction(action="policy_skip", memory_id="mem-4", detail="Skipped supersession link repair for append-only memory"),
                MaintenanceAction(action="dedup", memory_id="mem-3", detail="merge"),
            ],
            "dedup_found": 3,
            "owners_normalized": 2,
            "links_fixed": 1,
        })()
        with patch.object(main, "run_maintenance", new=AsyncMock(return_value=fake_report)):
            report = await main.maintain(req=object(), session=object(), _user={"sub": "tester"})

        self.assertEqual(report.dedup_found, 3)
        self.assertEqual(report.report_id, "audit-1")
        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 0,
            "superseded": 0,
            "archived": 0,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})
        self.assertEqual(snapshot["counters"]["maintain_runs_total"], 1)
        self.assertEqual(snapshot["counters"]["duplicate_candidates_total"], 3)
        self.assertEqual(snapshot["counters"]["owner_normalizations_total"], 2)
        self.assertEqual(snapshot["counters"]["orphaned_supersession_links_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_total"], 3)
        self.assertEqual(snapshot["counters"]["policy_skip_dedup_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_owner_normalization_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_link_repair_total"], 1)
        self.assertEqual(snapshot["gauges"]["policy_skip_per_maintain_run_ratio"], 3.0)
        self.assertEqual(snapshot["gauges"]["duplicate_candidates_per_maintain_run_ratio"], 3.0)
        self.assertEqual(snapshot["gauges"]["operational_health_status"], 2.0)
        self.assertEqual(snapshot["summary"]["health"], "elevated")
        self.assertEqual(snapshot["summary"]["health_status"], 2.0)
        self.assertEqual(snapshot["summary"]["thresholds"]["policy_skip_per_maintain_run_ratio"]["watch"], 0.25)

    async def test_prometheus_metrics_renders_counter_lines(self) -> None:
        fake_result = type("R", (), {"status": "created"})()
        with patch.object(main, "handle_memory_write", new=AsyncMock(return_value=fake_result)):
            await main.v1_write(
                req=MemoryWriteRequest(record=MemoryWriteRecord(content="x", domain="build", entity_type="Note")),
                session=object(),
                _user={"sub": "tester"},
            )
        fake_report = type("Report", (), {
            "report_id": "audit-2",
            "actions": [MaintenanceAction(action="policy_skip", memory_id="mem-9", detail="Skipped dedup mutation for append-only memory")],
            "dedup_found": 0,
            "owners_normalized": 0,
            "links_fixed": 0,
        })()
        with patch.object(main, "run_maintenance", new=AsyncMock(return_value=fake_report)):
            await main.maintain(req=object(), session=object(), _user={"sub": "tester"})

        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 7,
            "superseded": 2,
            "archived": 1,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 3, "superseded": 2, "archived": 0, "deleted": 0},
            "build": {"active": 4, "superseded": 0, "archived": 1, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            payload = await main.prometheus_metrics(session=object(), _user={"sub": "tester"})
        self.assertIn("# TYPE memories_created_total counter", payload)
        self.assertIn("memories_created_total 1", payload)
        self.assertIn("# TYPE active_memories_total gauge", payload)
        self.assertIn("active_memories_total 7", payload)
        self.assertIn("superseded_memories_total 2", payload)
        self.assertIn("active_memories_corporate_total 3", payload)
        self.assertIn("active_memories_build_total 4", payload)
        self.assertIn("# TYPE policy_skip_total counter", payload)
        self.assertIn("policy_skip_total 1", payload)
        self.assertIn("# TYPE policy_skip_dedup_total counter", payload)
        self.assertIn("policy_skip_dedup_total 1", payload)
        self.assertIn("# TYPE policy_skip_per_maintain_run_ratio gauge", payload)
        self.assertIn("policy_skip_per_maintain_run_ratio 1.0", payload)
        self.assertIn("# TYPE operational_health_status gauge", payload)
        self.assertIn("operational_health_status 2.0", payload)
        self.assertIn("policy_skip_per_maintain_run_ratio_watch_threshold 0.25", payload)

    async def test_delete_policy_skip_counts_reason_specific_metric(self) -> None:
        with patch.object(main, "get_memory", new=AsyncMock(return_value=main.MemoryOut(
            id="mem-1",
            tenant_id=None,
            domain="build",
            entity_type="Note",
            content="payload",
            owner="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            obsidian_ref=None,
            custom_fields={},
            content_hash="hash",
            match_key="mk-1",
            previous_id=None,
            root_id="mem-1",
            valid_from=None,
            created_at="2026-03-28T00:00:00Z",
            updated_at="2026-03-28T00:00:00Z",
            created_by="tester",
        ))), patch.object(main, "delete_memory", new=AsyncMock(side_effect=ValueError("Cannot hard-delete append-only memories."))):
            with self.assertRaises(HTTPException) as ctx:
                await main.delete(memory_id="mem-1", session=object(), _user={"sub": "tester"})

        self.assertEqual(ctx.exception.status_code, 403)
        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 0,
            "superseded": 0,
            "archived": 0,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})
        self.assertEqual(snapshot["counters"]["policy_skip_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_delete_total"], 1)
        self.assertEqual(snapshot["summary"]["health"], "normal")
        self.assertEqual(snapshot["summary"]["health_status"], 0.0)

    async def test_admin_access_denied_counts_metrics(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False):
            with self.assertRaises(HTTPException):
                await main.export(req=main.ExportRequest(ids=["mem-1"]), session=object(), _user={"sub": "tester"})

        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 0,
            "superseded": 0,
            "archived": 0,
            "deleted": 0,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "build": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
            "personal": {"active": 0, "superseded": 0, "archived": 0, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})

        self.assertEqual(snapshot["counters"]["access_denied_total"], 1)
        self.assertEqual(snapshot["counters"]["access_denied_admin_total"], 1)

    async def test_diagnostics_metrics_includes_live_gauges(self) -> None:
        with patch.object(main, "get_memory_status_counts", new=AsyncMock(return_value={
            "active": 11,
            "superseded": 4,
            "archived": 2,
            "deleted": 1,
        })), patch.object(main, "get_memory_domain_status_counts", new=AsyncMock(return_value={
            "corporate": {"active": 5, "superseded": 4, "archived": 0, "deleted": 0},
            "build": {"active": 4, "superseded": 0, "archived": 1, "deleted": 1},
            "personal": {"active": 2, "superseded": 0, "archived": 1, "deleted": 0},
        })):
            snapshot = await main.diagnostics_metrics(session=object(), _user={"sub": "tester"})

        self.assertEqual(snapshot["gauges"]["active_memories_total"], 11)
        self.assertEqual(snapshot["gauges"]["superseded_memories_total"], 4)
        self.assertEqual(snapshot["gauges"]["archived_memories_total"], 2)
        self.assertEqual(snapshot["gauges"]["deleted_memories_total"], 1)
        self.assertEqual(snapshot["gauges"]["active_memories_corporate_total"], 5)
        self.assertEqual(snapshot["gauges"]["active_memories_build_total"], 4)
        self.assertEqual(snapshot["gauges"]["active_memories_personal_total"], 2)
        self.assertEqual(snapshot["gauges"]["policy_skip_per_maintain_run_ratio"], 0.0)
        self.assertEqual(snapshot["gauges"]["search_zero_hit_ratio"], 0.0)
        self.assertEqual(snapshot["gauges"]["operational_health_status"], 0.0)
        self.assertEqual(snapshot["summary"]["health"], "normal")
        self.assertEqual(snapshot["summary"]["thresholds"]["search_zero_hit_ratio"]["elevated"], 0.15)


if __name__ == "__main__":
    unittest.main()
