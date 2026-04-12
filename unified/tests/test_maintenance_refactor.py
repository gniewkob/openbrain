"""Tests for _run_maintenance_inner sub-function contracts."""

from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestProcessDuplicates:
    @pytest.mark.asyncio
    async def test_returns_empty_when_threshold_zero(self):
        from src.memory_writes import _process_duplicates

        session = AsyncMock()
        actions, count = await _process_duplicates(
            session=session, dedup_threshold=0, total=5, dry_run=True
        )
        assert actions == []
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_total_le_one(self):
        from src.memory_writes import _process_duplicates

        session = AsyncMock()
        actions, count = await _process_duplicates(
            session=session, dedup_threshold=1, total=1, dry_run=True
        )
        assert actions == []
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_dup_groups(self):
        from src.memory_writes import _process_duplicates

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        actions, count = await _process_duplicates(
            session=session, dedup_threshold=1, total=5, dry_run=True
        )
        assert actions == []
        assert count == 0


class TestNormalizeOwners:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_mapping(self):
        from src.memory_writes import _normalize_owners

        session = AsyncMock()
        actions, count = await _normalize_owners(
            session=session, normalize_owners={}, dry_run=True
        )
        assert actions == []
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_mapping(self):
        from src.memory_writes import _normalize_owners

        session = AsyncMock()
        actions, count = await _normalize_owners(
            session=session, normalize_owners=None, dry_run=True
        )
        assert actions == []
        assert count == 0


class TestFixSupersededLinks:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_superseded(self):
        from src.memory_writes import _fix_superseded_links

        session = AsyncMock()
        # active_ids query, then superseded query
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=lambda: []),
                MagicMock(scalars=lambda: MagicMock(all=lambda: [])),
            ]
        )
        actions, count = await _fix_superseded_links(session=session, dry_run=True)
        assert actions == []
        assert count == 0


class TestRunMaintenanceInnerIntegration:
    @pytest.mark.asyncio
    async def test_returns_maintenance_report(self):
        from src.memory_writes import _run_maintenance_inner
        from src.schemas import MaintenanceRequest, MaintenanceReport

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0))
        req = MaintenanceRequest(dry_run=True, dedup_threshold=0)
        report = await _run_maintenance_inner(session=session, req=req, actor="test")
        assert isinstance(report, MaintenanceReport)
        assert report.dry_run is True
        assert report.total_scanned == 0
