"""Boundary value tests for schema limits (TEST-004).

Pure Pydantic model tests — no DB, no HTTP required.
All tests must run in < 500ms.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest

from pydantic import ValidationError

from src.schemas import (
    MAX_BULK_RECORDS,
    MAX_CONTENT_LEN,
    MAX_ENTITY_TYPE_LEN,
    MAX_TAGS,
    MemoryWriteManyRequest,
    MemoryWriteRequest,
    SyncCheckRequest,
)

# ---------------------------------------------------------------------------
# Load mcp-gateway src/main.py under a unique package name to avoid shadowing
# unified/src/main.py (both packages use the name "src").
# ---------------------------------------------------------------------------
_GW_DIR = "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway"

_pkg_spec = importlib.util.spec_from_file_location(
    "mcp_gw_src",
    _GW_DIR + "/src/__init__.py",
    submodule_search_locations=[_GW_DIR + "/src"],
)
_pkg_mod = importlib.util.module_from_spec(_pkg_spec)  # type: ignore[arg-type]
sys.modules["mcp_gw_src"] = _pkg_mod
_pkg_spec.loader.exec_module(_pkg_mod)  # type: ignore[union-attr]

_obs_spec = importlib.util.spec_from_file_location(
    "mcp_gw_src.obsidian_cli",
    _GW_DIR + "/src/obsidian_cli.py",
)
_obs_mod = importlib.util.module_from_spec(_obs_spec)  # type: ignore[arg-type]
sys.modules["mcp_gw_src.obsidian_cli"] = _obs_mod
_obs_spec.loader.exec_module(_obs_mod)  # type: ignore[union-attr]

_main_spec = importlib.util.spec_from_file_location(
    "mcp_gw_src.main",
    _GW_DIR + "/src/main.py",
)
_main_mod = importlib.util.module_from_spec(_main_spec)  # type: ignore[arg-type]
sys.modules["mcp_gw_src.main"] = _main_mod
_main_spec.loader.exec_module(_main_mod)  # type: ignore[union-attr]

_gw_brain_search = _main_mod.brain_search  # type: ignore[attr-defined]
_gw_brain_list = _main_mod.brain_list  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_record(**overrides) -> dict:
    """Minimal valid MemoryWriteRecord payload."""
    base = {
        "domain": "build",
        "entity_type": "Note",
        "content": "x",
    }
    base.update(overrides)
    return base


def _minimal_write(**overrides) -> dict:
    """Minimal valid MemoryWriteRequest payload (wraps the record field)."""
    return {"record": _minimal_record(**overrides)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContentLengthBoundary(unittest.TestCase):
    def test_content_empty_passes(self):
        # ContentStr = Annotated[str, Field(max_length=MAX_CONTENT_LEN)] — no min_length.
        # Empty string is valid at the schema level.
        MemoryWriteRequest.model_validate(_minimal_write(content=""))

    def test_content_at_max_passes(self):
        MemoryWriteRequest.model_validate(_minimal_write(content="a" * MAX_CONTENT_LEN))

    def test_content_over_max_raises(self):
        with self.assertRaises(ValidationError):
            MemoryWriteRequest.model_validate(
                _minimal_write(content="a" * (MAX_CONTENT_LEN + 1))
            )


class TestEntityTypeLengthBoundary(unittest.TestCase):
    def test_entity_type_at_max_passes(self):
        MemoryWriteRequest.model_validate(
            _minimal_write(entity_type="A" * MAX_ENTITY_TYPE_LEN)
        )

    def test_entity_type_over_max_raises(self):
        with self.assertRaises(ValidationError):
            MemoryWriteRequest.model_validate(
                _minimal_write(entity_type="A" * (MAX_ENTITY_TYPE_LEN + 1))
            )


class TestTagsListBoundary(unittest.TestCase):
    def test_tags_at_max_passes(self):
        MemoryWriteRequest.model_validate(
            _minimal_write(tags=[f"tag{i}" for i in range(MAX_TAGS)])
        )

    def test_tags_over_max_raises(self):
        with self.assertRaises(ValidationError):
            MemoryWriteRequest.model_validate(
                _minimal_write(tags=[f"tag{i}" for i in range(MAX_TAGS + 1)])
            )


class TestBulkRecordLimitBoundary(unittest.TestCase):
    def test_bulk_at_max_passes(self):
        records = [
            _minimal_record(content=f"record {i}") for i in range(MAX_BULK_RECORDS)
        ]
        MemoryWriteManyRequest.model_validate({"records": records})

    def test_bulk_over_max_raises(self):
        records = [
            _minimal_record(content=f"record {i}") for i in range(MAX_BULK_RECORDS + 1)
        ]
        with self.assertRaises(ValidationError):
            MemoryWriteManyRequest.model_validate({"records": records})


class TestSyncCheckRequestValidator(unittest.TestCase):
    """SyncCheckRequest requires exactly one of: memory_id, match_key, obsidian_ref."""

    def test_all_identifiers_none_raises(self):
        with self.assertRaises(ValidationError):
            SyncCheckRequest.model_validate({})

    def test_two_identifiers_raises(self):
        with self.assertRaises(ValidationError):
            SyncCheckRequest.model_validate({"memory_id": "abc", "match_key": "key"})

    def test_exactly_memory_id_passes(self):
        SyncCheckRequest.model_validate({"memory_id": "abc"})

    def test_exactly_match_key_passes(self):
        SyncCheckRequest.model_validate({"match_key": "some-key"})

    def test_exactly_obsidian_ref_passes(self):
        SyncCheckRequest.model_validate({"obsidian_ref": "vault/Note.md"})

    def test_file_hash_alone_raises(self):
        # file_hash is NOT one of the three checked identifiers — providing only
        # file_hash still counts as zero valid identifiers.
        with self.assertRaises(ValidationError):
            SyncCheckRequest.model_validate({"file_hash": "sha256:abc"})

    def test_memory_id_with_file_hash_passes(self):
        # file_hash is an auxiliary field; combining with a valid identifier is OK.
        SyncCheckRequest.model_validate({"memory_id": "abc", "file_hash": "sha256:abc"})


class TestGatewayParameterBounds(unittest.TestCase):
    """Validation of gateway parameter bounds (PERF-007 guards)."""

    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def test_search_top_k_zero_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._run(_gw_brain_search(query="test", top_k=0))

    def test_search_top_k_over_limit_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._run(_gw_brain_search(query="test", top_k=101))

    def test_search_top_k_min_passes(self):
        try:
            self._run(_gw_brain_search(query="test", top_k=1))
        except ValueError as exc:
            if "top_k must" in str(exc):
                self.fail("top_k=1 should not raise bounds ValueError")
        except Exception:
            pass  # HTTP/network failure is OK in unit context

    def test_search_top_k_max_passes(self):
        try:
            self._run(_gw_brain_search(query="test", top_k=100))
        except ValueError as exc:
            if "top_k must" in str(exc):
                self.fail("top_k=100 should not raise bounds ValueError")
        except Exception:
            pass

    def test_list_limit_zero_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._run(_gw_brain_list(limit=0))

    def test_list_limit_over_max_raises_value_error(self):
        # MAX_LIST_LIMIT = 200; 201 must raise
        with self.assertRaises(ValueError):
            self._run(_gw_brain_list(limit=201))


if __name__ == "__main__":
    unittest.main()
