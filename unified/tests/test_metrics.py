"""Tests for telemetry metrics - testing core functions directly."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from src.telemetry import get_metrics_snapshot, reset_metrics, incr_metric


class MetricsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_metrics()

    async def test_metrics_increment_and_reset(self) -> None:
        """Test basic metrics increment and reset functionality."""
        # Increment some metrics
        incr_metric("memories_created_total")
        incr_metric("memories_created_total")
        incr_metric("sync_checks_total")
        
        snapshot = get_metrics_snapshot()
        self.assertEqual(snapshot["counters"]["memories_created_total"], 2)
        self.assertEqual(snapshot["counters"]["sync_checks_total"], 1)
        
        # Reset and verify
        reset_metrics()
        snapshot = get_metrics_snapshot()
        self.assertEqual(snapshot["counters"]["memories_created_total"], 0)
        self.assertEqual(snapshot["counters"]["sync_checks_total"], 0)

    async def test_maintain_counts_hygiene_metrics(self) -> None:
        """Test that maintenance actions are tracked in metrics."""
        # Simulate maintenance actions through metrics
        incr_metric("maintain_runs_total")
        incr_metric("duplicate_candidates_total", 3)
        incr_metric("owner_normalizations_total", 2)
        incr_metric("orphaned_supersession_links_total", 1)
        incr_metric("policy_skip_total", 3)
        incr_metric("policy_skip_dedup_total", 1)
        incr_metric("policy_skip_owner_normalization_total", 1)
        incr_metric("policy_skip_link_repair_total", 1)
        
        snapshot = get_metrics_snapshot()
        self.assertEqual(snapshot["counters"]["maintain_runs_total"], 1)
        self.assertEqual(snapshot["counters"]["duplicate_candidates_total"], 3)
        self.assertEqual(snapshot["counters"]["owner_normalizations_total"], 2)
        self.assertEqual(snapshot["counters"]["orphaned_supersession_links_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_total"], 3)

    async def test_access_denied_metrics(self) -> None:
        """Test access denied metrics tracking."""
        incr_metric("access_denied_total")
        incr_metric("access_denied_admin_total")
        
        snapshot = get_metrics_snapshot()
        self.assertEqual(snapshot["counters"]["access_denied_total"], 1)
        self.assertEqual(snapshot["counters"]["access_denied_admin_total"], 1)

    async def test_delete_policy_skip_metrics(self) -> None:
        """Test delete policy skip metrics."""
        incr_metric("policy_skip_total")
        incr_metric("policy_skip_delete_total")
        
        snapshot = get_metrics_snapshot()
        self.assertEqual(snapshot["counters"]["policy_skip_total"], 1)
        self.assertEqual(snapshot["counters"]["policy_skip_delete_total"], 1)

    async def test_diagnostics_metrics_structure(self) -> None:
        """Test that diagnostics metrics has correct structure."""
        # Set up some metrics
        incr_metric("memories_created_total", 5)
        incr_metric("memories_versioned_total", 3)
        incr_metric("sync_checks_total", 10)
        incr_metric("sync_exists_total", 8)
        
        snapshot = get_metrics_snapshot()
        
        # Check structure
        self.assertIn("counters", snapshot)
        self.assertIn("gauges", snapshot)
        self.assertIn("histograms", snapshot)
        
        # Check specific counters
        self.assertEqual(snapshot["counters"]["memories_created_total"], 5)
        self.assertEqual(snapshot["counters"]["memories_versioned_total"], 3)


if __name__ == "__main__":
    unittest.main()
