"""Tests for gateway parameter validation (PERF-007).

Pure unit tests — no HTTP, no DB required.
ValueError is expected before any HTTP call is made.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_TESTS = ROOT / "mcp-gateway" / "tests"
if str(GATEWAY_TESTS) not in sys.path:
    sys.path.insert(0, str(GATEWAY_TESTS))

from helpers import load_gateway_main  # noqa: E402

try:
    _gateway = load_gateway_main()
    _GATEWAY_IMPORT_ERROR = None
except Exception as exc:
    _gateway = None
    _GATEWAY_IMPORT_ERROR = exc


def _skip_if_no_gateway(test_cls):
    if _GATEWAY_IMPORT_ERROR is not None:
        return unittest.skip(f"gateway import failed: {_GATEWAY_IMPORT_ERROR}")(
            test_cls
        )
    return test_cls


def _run(coro):
    return asyncio.run(coro)


@_skip_if_no_gateway
class TestBrainSearchValidation(unittest.TestCase):
    def test_search_top_k_zero_raises(self):
        with self.assertRaisesRegex(ValueError, "top_k"):
            _run(_gateway.brain_search(query="test", top_k=0))

    def test_search_top_k_over_limit_raises(self):
        with self.assertRaisesRegex(ValueError, "top_k"):
            _run(_gateway.brain_search(query="test", top_k=_gateway.MAX_SEARCH_TOP_K + 1))

    def test_search_top_k_boundary_min_passes(self):
        try:
            _run(_gateway.brain_search(query="test", top_k=1))
        except ValueError as exc:
            if "top_k" in str(exc):
                self.fail("top_k=1 should not raise validation ValueError")
        except Exception:
            pass  # HTTP failure OK — validation passed

    def test_search_top_k_boundary_max_passes(self):
        try:
            _run(_gateway.brain_search(query="test", top_k=_gateway.MAX_SEARCH_TOP_K))
        except ValueError as exc:
            if "top_k" in str(exc):
                self.fail("top_k=max should not raise validation ValueError")
        except Exception:
            pass


@_skip_if_no_gateway
class TestBrainListValidation(unittest.TestCase):
    def test_list_limit_zero_raises(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            _run(_gateway.brain_list(limit=0))

    def test_list_limit_over_max_raises(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            _run(_gateway.brain_list(limit=_gateway.MAX_LIST_LIMIT + 1))

    def test_list_limit_boundary_min_passes(self):
        try:
            _run(_gateway.brain_list(limit=1))
        except ValueError as exc:
            if "limit" in str(exc) and "must be" in str(exc):
                self.fail("limit=1 should not raise validation ValueError")
        except Exception:
            pass

    def test_list_limit_boundary_max_passes(self):
        try:
            _run(_gateway.brain_list(limit=_gateway.MAX_LIST_LIMIT))
        except ValueError as exc:
            if "limit" in str(exc) and "must be" in str(exc):
                self.fail("limit=max should not raise validation ValueError")
        except Exception:
            pass


@_skip_if_no_gateway
class TestBrainObsidianSyncValidation(unittest.TestCase):
    def test_sync_limit_zero_raises(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            _run(_gateway.brain_obsidian_sync(limit=0))

    def test_sync_limit_over_max_raises(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            _run(_gateway.brain_obsidian_sync(limit=_gateway.MAX_SYNC_LIMIT + 1))


@_skip_if_no_gateway
class TestBrainObsidianCollectionValidation(unittest.TestCase):
    def test_collection_max_items_zero_raises(self):
        with self.assertRaisesRegex(ValueError, "max_items"):
            _run(
                _gateway.brain_obsidian_collection(
                    query="test", collection_name="col", max_items=0
                )
            )

    def test_collection_max_items_over_limit_raises(self):
        with self.assertRaisesRegex(ValueError, "max_items"):
            _run(
                _gateway.brain_obsidian_collection(
                    query="test",
                    collection_name="col",
                    max_items=_gateway.MAX_SYNC_LIMIT + 1,
                )
            )


if __name__ == "__main__":
    unittest.main()
