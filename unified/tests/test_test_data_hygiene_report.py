from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src import memory_reads


class TestDataHygieneReportReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_test_data_hygiene_report_maps_counts_and_sample(self) -> None:
        now = datetime.now(timezone.utc)

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: 11),  # total
                SimpleNamespace(scalar=lambda: 9),  # active
                SimpleNamespace(scalar=lambda: 7),  # build active
                SimpleNamespace(scalar=lambda: 1),  # corporate active
                SimpleNamespace(scalar=lambda: 1),  # personal active
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
                SimpleNamespace(all=lambda: [("test", 6), ("openbrain-bulk-test", 2)]),
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

        report = await memory_reads.get_test_data_hygiene_report(session, sample_limit=5)

        self.assertEqual(report.sample_limit, 5)
        self.assertEqual(report.hidden_counts["hidden_test_data_total"], 11)
        self.assertEqual(report.status_counts["active"], 9)
        self.assertEqual(report.domain_status_counts["build"]["active"], 7)
        self.assertEqual(report.top_owners["tester"], 8)
        self.assertEqual(report.match_key_prefix_counts["test"], 6)
        self.assertEqual(report.null_match_key_count, 1)
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
            hidden_counts={"hidden_test_data_total": 3},
            status_counts={"active": 3},
            domain_status_counts={"build": {"active": 3}},
            top_owners={"tester": 3},
            match_key_prefix_counts={"test": 2},
            null_match_key_count=1,
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


if __name__ == "__main__":
    unittest.main()
