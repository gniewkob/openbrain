from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src import memory_reads
from src.schemas import TestDataActionSuggestion as HygieneActionSuggestion


class TestDataHygieneReportReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_test_data_hygiene_report_maps_counts_and_sample(self) -> None:
        now = datetime.now(timezone.utc)

        session = AsyncMock()
        with (
            patch.object(
                memory_reads,
                "get_memory_status_counts",
                new=AsyncMock(return_value={"active": 6, "superseded": 1}),
            ),
            patch.object(
                memory_reads,
                "get_memory_domain_status_counts",
                new=AsyncMock(
                    return_value={
                        "build": {"active": 4},
                        "corporate": {"active": 1},
                        "personal": {"active": 1},
                    }
                ),
            ),
            patch.object(
                memory_reads,
                "get_hidden_test_data_counts",
                new=AsyncMock(
                    return_value={
                        "hidden_test_data_total": 11,
                        "hidden_test_data_active_total": 9,
                        "hidden_test_data_build_total": 7,
                        "hidden_test_data_corporate_total": 1,
                        "hidden_test_data_personal_total": 1,
                    }
                ),
            ),
        ):
            session.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(all=lambda: [("active", 9), ("superseded", 2)]),
                    SimpleNamespace(
                        all=lambda: [
                            ("build", "active", 7),
                            ("corporate", "active", 1),
                            ("personal", "active", 1),
                            ("build", "superseded", 2),
                        ]
                    ),
                    SimpleNamespace(all=lambda: [("tester", 8), ("ci-bot", 3)]),
                    SimpleNamespace(
                        all=lambda: [("test", 6), ("openbrain-bulk-test", 2)]
                    ),
                    SimpleNamespace(scalar=lambda: 1),
                    SimpleNamespace(
                        all=lambda: [
                            SimpleNamespace(
                                id="mem-1",
                                domain="build",
                                status="active",
                                owner="tester",
                                match_key="mk:1",
                                created_at=now,
                                updated_at=now,
                            )
                        ]
                    ),
                ]
            )
            report = await memory_reads.get_test_data_hygiene_report(
                session, sample_limit=5
            )

        self.assertEqual(report.sample_limit, 5)
        self.assertEqual(report.visible_status_counts["active"], 6)
        self.assertEqual(report.visible_domain_status_counts["build"]["active"], 4)
        self.assertEqual(report.hidden_counts["hidden_test_data_total"], 11)
        self.assertEqual(report.hidden_active_ratio, 0.6)
        self.assertEqual(report.hidden_active_ratio_by_domain["build"], 0.6364)
        self.assertEqual(report.status_counts["active"], 9)
        self.assertEqual(report.domain_status_counts["build"]["active"], 7)
        self.assertEqual(report.top_owners["tester"], 8)
        self.assertEqual(report.match_key_prefix_counts["test"], 6)
        self.assertEqual(report.null_match_key_count, 1)
        action_codes = {item.code for item in report.recommended_actions}
        self.assertIn("cleanup_build_test_data", action_codes)
        self.assertIn("hidden_ratio_elevated", action_codes)
        self.assertIn("normalize_missing_match_keys", action_codes)
        self.assertIn("owner_feedback_loop", action_codes)
        self.assertEqual(len(report.sample), 1)
        self.assertEqual(report.sample[0].id, "mem-1")


class TestDataHygieneReportEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_requires_admin(self) -> None:
        from src.api.v1 import memory as mem_module

        with patch.object(
            mem_module,
            "require_admin",
            side_effect=HTTPException(status_code=403, detail="Admin privileges required"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mem_module.test_data_hygiene_report(
                    sample_limit=10,
                    session=object(),
                    _user={"sub": "non-admin"},
                )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_endpoint_returns_hygiene_report(self) -> None:
        from src.api.v1 import memory as mem_module

        now = datetime.now(timezone.utc)
        fake_report = mem_module.TestDataHygieneReport(
            generated_at=now,
            sample_limit=3,
            visible_status_counts={"active": 7},
            visible_domain_status_counts={"build": {"active": 5}},
            hidden_counts={"hidden_test_data_total": 3},
            status_counts={"active": 3},
            domain_status_counts={"build": {"active": 3}},
            top_owners={"tester": 3},
            match_key_prefix_counts={"test": 2},
            null_match_key_count=1,
            recommended_actions=[
                HygieneActionSuggestion(
                    code="cleanup_build_test_data",
                    priority="high",
                    summary="cleanup",
                )
            ],
            sample=[],
        )

        with (
            patch.object(mem_module, "require_admin"),
            patch.object(
                mem_module,
                "get_test_data_hygiene_report",
                new=AsyncMock(return_value=fake_report),
            ),
        ):
            result = await mem_module.test_data_hygiene_report(
                sample_limit=3,
                session=object(),
                _user={"sub": "admin"},
            )

        self.assertEqual(result.sample_limit, 3)
        self.assertEqual(result.hidden_counts["hidden_test_data_total"], 3)

    async def test_get_test_data_hygiene_report_returns_no_action_for_empty_state(
        self,
    ) -> None:
        now = datetime.now(timezone.utc)
        session = AsyncMock()
        with (
            patch.object(
                memory_reads,
                "get_memory_status_counts",
                new=AsyncMock(return_value={"active": 0}),
            ),
            patch.object(
                memory_reads,
                "get_memory_domain_status_counts",
                new=AsyncMock(
                    return_value={
                        "build": {"active": 0},
                        "corporate": {"active": 0},
                        "personal": {"active": 0},
                    }
                ),
            ),
            patch.object(
                memory_reads,
                "get_hidden_test_data_counts",
                new=AsyncMock(
                    return_value={
                        "hidden_test_data_total": 0,
                        "hidden_test_data_active_total": 0,
                        "hidden_test_data_build_total": 0,
                        "hidden_test_data_corporate_total": 0,
                        "hidden_test_data_personal_total": 0,
                    }
                ),
            ),
        ):
            session.execute = AsyncMock(
                side_effect=[
                    SimpleNamespace(all=lambda: []),  # status counts
                    SimpleNamespace(all=lambda: []),  # domain counts
                    SimpleNamespace(all=lambda: []),  # top owners
                    SimpleNamespace(all=lambda: []),  # prefix counts
                    SimpleNamespace(scalar=lambda: 0),  # null match key
                    SimpleNamespace(all=lambda: []),  # sample
                ]
            )
            report = await memory_reads.get_test_data_hygiene_report(
                session, sample_limit=5
            )
        self.assertEqual(report.hidden_active_ratio, 0.0)
        self.assertEqual(report.hidden_active_ratio_by_domain["build"], 0.0)
        self.assertEqual(len(report.recommended_actions), 1)
        self.assertEqual(report.recommended_actions[0].code, "no_action_needed")
        self.assertEqual(report.recommended_actions[0].priority, "low")


if __name__ == "__main__":
    unittest.main()
