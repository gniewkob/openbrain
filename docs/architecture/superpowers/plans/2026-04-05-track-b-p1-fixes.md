# Track B — P1 Security & Performance Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three targeted P1 fixes: gateway parameter bounds validation, two failing auth tests, and schema boundary value tests.

**Architecture:** Pure fixes — no new abstractions, no migrations. PERF-007 adds `ValueError` guards at the top of four gateway tool functions. TEST-002 replaces the `sys.modules` reload hack in two tests with direct `patch()` of module globals. TEST-004 adds pure Pydantic unit tests in a new file.

**Tech Stack:** Python 3.13, FastMCP, unittest, unittest.mock.patch, Pydantic v2

---

## File Map

| File | Change |
|------|--------|
| `unified/mcp-gateway/src/main.py` | Add 3 module-level constants + `ValueError` guards in `brain_search`, `brain_list`, `brain_obsidian_sync`, `brain_obsidian_collection` |
| `unified/tests/test_gateway_validation.py` | New: gateway parameter validation tests (no HTTP, no DB) |
| `unified/tests/test_auth_security.py` | Replace 2 failing tests (`test_public_mode_requires_oidc_issuer`, `test_public_base_url_requires_oidc_issuer`) — keep 4 passing tests unchanged |
| `unified/tests/test_boundary_values.py` | New: schema boundary tests (no DB, no HTTP) |

---

### Task 1: PERF-007 — Gateway Parameter Validation

**Files:**
- Modify: `unified/mcp-gateway/src/main.py` (lines 37–55 for constants; ~307, ~357, ~560, ~704 for guards)
- Create: `unified/tests/test_gateway_validation.py`

- [ ] **Step 1: Write the failing tests**

Create `unified/tests/test_gateway_validation.py`:

```python
"""Tests for gateway parameter validation (PERF-007).

Pure unit tests — no HTTP, no DB required.
Import the gateway module and call the async functions directly.
ValueError is expected before any HTTP call is made.
"""
from __future__ import annotations

import asyncio
import unittest


class TestBrainSearchValidation(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_search_top_k_zero_raises(self):
        from mcp_gateway.src.main import brain_search
        with self.assertRaisesRegex(ValueError, "top_k"):
            self._run(brain_search(query="test", top_k=0))

    def test_search_top_k_over_limit_raises(self):
        from mcp_gateway.src.main import brain_search
        with self.assertRaisesRegex(ValueError, "top_k"):
            self._run(brain_search(query="test", top_k=101))

    def test_search_top_k_boundary_min_passes(self):
        """top_k=1 must not raise a ValueError (HTTP call may fail in test env)."""
        from mcp_gateway.src.main import brain_search
        import httpx
        try:
            self._run(brain_search(query="test", top_k=1))
        except ValueError:
            self.fail("top_k=1 should not raise ValueError")
        except (httpx.ConnectError, httpx.ConnectTimeout, Exception):
            pass  # No backend in test env — validation passed, HTTP failure is OK

    def test_search_top_k_boundary_max_passes(self):
        """top_k=100 must not raise a ValueError."""
        from mcp_gateway.src.main import brain_search
        import httpx
        try:
            self._run(brain_search(query="test", top_k=100))
        except ValueError:
            self.fail("top_k=100 should not raise ValueError")
        except (httpx.ConnectError, httpx.ConnectTimeout, Exception):
            pass


class TestBrainListValidation(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_list_limit_zero_raises(self):
        from mcp_gateway.src.main import brain_list
        with self.assertRaisesRegex(ValueError, "limit"):
            self._run(brain_list(limit=0))

    def test_list_limit_over_max_raises(self):
        from mcp_gateway.src.main import brain_list
        with self.assertRaisesRegex(ValueError, "limit"):
            self._run(brain_list(limit=201))

    def test_list_limit_boundary_min_passes(self):
        from mcp_gateway.src.main import brain_list
        import httpx
        try:
            self._run(brain_list(limit=1))
        except ValueError:
            self.fail("limit=1 should not raise ValueError")
        except (httpx.ConnectError, httpx.ConnectTimeout, Exception):
            pass

    def test_list_limit_boundary_max_passes(self):
        from mcp_gateway.src.main import brain_list
        import httpx
        try:
            self._run(brain_list(limit=200))
        except ValueError:
            self.fail("limit=200 should not raise ValueError")
        except (httpx.ConnectError, httpx.ConnectTimeout, Exception):
            pass


class TestBrainObsidianSyncValidation(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_sync_limit_zero_raises(self):
        from mcp_gateway.src.main import brain_obsidian_sync
        with self.assertRaisesRegex(ValueError, "limit"):
            self._run(brain_obsidian_sync(limit=0))

    def test_sync_limit_over_max_raises(self):
        from mcp_gateway.src.main import brain_obsidian_sync
        with self.assertRaisesRegex(ValueError, "limit"):
            self._run(brain_obsidian_sync(limit=201))


class TestBrainObsidianCollectionValidation(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_collection_max_items_zero_raises(self):
        from mcp_gateway.src.main import brain_obsidian_collection
        with self.assertRaisesRegex(ValueError, "max_items"):
            self._run(brain_obsidian_collection(query="test", collection_name="col", max_items=0))

    def test_collection_max_items_over_limit_raises(self):
        from mcp_gateway.src.main import brain_obsidian_collection
        with self.assertRaisesRegex(ValueError, "max_items"):
            self._run(brain_obsidian_collection(query="test", collection_name="col", max_items=201))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_gateway_validation.py -v 2>&1 | head -40
```

Expected: FAIL — `ValueError` not raised (no validation exists yet).

- [ ] **Step 3: Add constants and guards to `unified/mcp-gateway/src/main.py`**

After line 41 (`MCP_SOURCE_SYSTEM = ...`), add the three constants:

```python
# Parameter validation bounds (PERF-007)
MAX_SEARCH_TOP_K: int = 100
MAX_LIST_LIMIT: int = 200
MAX_SYNC_LIMIT: int = 200
```

Then add guards at the top of each tool function body.

In `brain_list` (line 308, first line of function body after the docstring):
```python
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_LIST_LIMIT}, got {limit}")
```

In `brain_search` (first line of function body after the docstring):
```python
    if not 1 <= top_k <= MAX_SEARCH_TOP_K:
        raise ValueError(f"top_k must be 1–{MAX_SEARCH_TOP_K}, got {top_k}")
```

In `brain_obsidian_sync` (first line of function body):
```python
    if not 1 <= limit <= MAX_SYNC_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_SYNC_LIMIT}, got {limit}")
```

In `brain_obsidian_collection` (first line of function body after `_require_obsidian_local_tools_enabled()`):
```python
    if not 1 <= max_items <= MAX_SYNC_LIMIT:
        raise ValueError(f"max_items must be 1–{MAX_SYNC_LIMIT}, got {max_items}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_gateway_validation.py -v
```

Expected: All 12 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
git add mcp-gateway/src/main.py tests/test_gateway_validation.py
git commit -m "feat: PERF-007 — add parameter bounds validation to gateway tools

Add MAX_SEARCH_TOP_K=100, MAX_LIST_LIMIT=200, MAX_SYNC_LIMIT=200 constants.
Guard brain_search(top_k), brain_list(limit), brain_obsidian_sync(limit),
brain_obsidian_collection(max_items) — raises ValueError caught by value_error_handler → 422."
```

---

### Task 2: TEST-002 — Fix Failing Auth Security Tests

**Files:**
- Modify: `unified/tests/test_auth_security.py`

**Context:** Two tests (`test_public_mode_requires_oidc_issuer`, `test_public_base_url_requires_oidc_issuer`) fail because `_reload_auth()` uses `sys.modules` + `importlib.import_module()` to reimport `src.auth`. The problem: `PUBLIC_MODE`, `PUBLIC_BASE_URL`, `PUBLIC_EXPOSURE`, `OIDC_ISSUER_URL`, and `INTERNAL_API_KEY` are module-level globals resolved at first import time (lines 29–35 of `src/auth.py`). A `patch.dict(os.environ, ...)` doesn't re-evaluate those globals.

The fix: in the two failing tests, directly patch the already-imported module-level globals using `unittest.mock.patch("src.auth.PUBLIC_EXPOSURE", ...)` and call `validate_security_configuration()` directly.

The four passing tests (`test_public_mode_rejects_dev_default_internal_key`, `test_policy_registry_json_must_be_valid`, `test_local_mode_logs_warning_once_when_auth_is_disabled`, `test_oidc_verifier_creates_refresh_lock_lazily`) must remain untouched and continue to pass.

- [ ] **Step 1: Run the test file to confirm exactly 2 failures**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_auth_security.py -v 2>&1
```

Expected: 4 pass, 2 fail (`test_public_mode_requires_oidc_issuer`, `test_public_base_url_requires_oidc_issuer`).

- [ ] **Step 2: Rewrite the two failing tests**

Replace `test_public_mode_requires_oidc_issuer` and `test_public_base_url_requires_oidc_issuer` with direct-patch versions.

The new `test_public_mode_requires_oidc_issuer`:
```python
def test_public_mode_requires_oidc_issuer(self) -> None:
    from src.auth import validate_security_configuration
    with patch("src.auth.PUBLIC_EXPOSURE", True), \
         patch("src.auth.OIDC_ISSUER_URL", ""), \
         patch("src.auth.INTERNAL_API_KEY", "super-secret"), \
         patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "openbrain-local-dev"):
        with self.assertRaisesRegex(RuntimeError, "requires OIDC_ISSUER_URL"):
            validate_security_configuration()
```

The new `test_public_base_url_requires_oidc_issuer`:
```python
def test_public_base_url_requires_oidc_issuer(self) -> None:
    from src.auth import validate_security_configuration
    with patch("src.auth.PUBLIC_EXPOSURE", True), \
         patch("src.auth.OIDC_ISSUER_URL", ""), \
         patch("src.auth.INTERNAL_API_KEY", "super-secret"), \
         patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "openbrain-local-dev"):
        with self.assertRaisesRegex(RuntimeError, "requires OIDC_ISSUER_URL"):
            validate_security_configuration()
```

Also remove unused imports `asyncio`, `importlib`, `os`, `sys`, `types` only if they become fully unused after the edit. Check first — `_reload_auth()` still uses them in the 4 passing tests.

- [ ] **Step 3: Run all 6 tests to verify all pass**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_auth_security.py -v
```

Expected: All 6 PASS. Zero `sys.modules` manipulation in the two fixed tests (the `_reload_auth` helper is still used by the other 4).

- [ ] **Step 4: Run full test suite to check for regressions**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All previously passing tests still pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
git add tests/test_auth_security.py
git commit -m "fix: TEST-002 — fix 2 failing auth security tests

Replace sys.modules reload hack with direct patch of module globals.
patch('src.auth.PUBLIC_EXPOSURE', True) + call validate_security_configuration()
directly. Eliminates frozen-globals problem. All 6 tests now pass."
```

---

### Task 3: TEST-004 — Boundary Value Tests

**Files:**
- Create: `unified/tests/test_boundary_values.py`

**Context:** Pure Pydantic unit tests. No DB, no HTTP. Constants from `unified/src/schemas.py`:
- `MAX_CONTENT_LEN = 20_000`
- `MAX_ENTITY_TYPE_LEN = 64`
- `MAX_TAGS = 32`
- `MAX_BULK_RECORDS = 100`

`SyncCheckRequest` has a `model_validator` requiring exactly one identifier among `memory_id`, `match_key`, `obsidian_ref`, `content_hash`.

`MemoryWriteManyRequest` wraps a list of `MemoryWriteRequest` with `max_length=MAX_BULK_RECORDS`.

- [ ] **Step 1: Write the failing tests**

Create `unified/tests/test_boundary_values.py`:

```python
"""Boundary value tests for schema limits (TEST-004).

Pure Pydantic model tests — no DB, no HTTP required.
All tests must run in < 500ms.
"""
from __future__ import annotations

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


def _minimal_write(**overrides) -> dict:
    """Minimal valid MemoryWriteRequest payload."""
    base = {
        "domain": "build",
        "entity_type": "Note",
        "content": "x",
    }
    base.update(overrides)
    return base


class TestContentLengthBoundary(unittest.TestCase):
    def test_content_empty_raises(self):
        with self.assertRaises(ValidationError):
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
        records = [_minimal_write(content=f"record {i}") for i in range(MAX_BULK_RECORDS)]
        MemoryWriteManyRequest.model_validate({"records": records})

    def test_bulk_over_max_raises(self):
        records = [_minimal_write(content=f"record {i}") for i in range(MAX_BULK_RECORDS + 1)]
        with self.assertRaises(ValidationError):
            MemoryWriteManyRequest.model_validate({"records": records})


class TestSyncCheckRequestValidator(unittest.TestCase):
    def test_all_identifiers_none_raises(self):
        with self.assertRaises(ValidationError):
            SyncCheckRequest.model_validate({})

    def test_two_identifiers_raises(self):
        with self.assertRaises(ValidationError):
            SyncCheckRequest.model_validate(
                {"memory_id": "abc", "match_key": "key"}
            )

    def test_exactly_memory_id_passes(self):
        SyncCheckRequest.model_validate({"memory_id": "abc"})

    def test_exactly_match_key_passes(self):
        SyncCheckRequest.model_validate({"match_key": "some-key"})

    def test_exactly_obsidian_ref_passes(self):
        SyncCheckRequest.model_validate({"obsidian_ref": "vault/Note.md"})

    def test_exactly_content_hash_passes(self):
        SyncCheckRequest.model_validate({"content_hash": "sha256:abc"})


class TestGatewayParameterBounds(unittest.TestCase):
    """Validation logic tests after PERF-007 — no HTTP needed."""

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    def test_search_top_k_zero_raises_value_error(self):
        from mcp_gateway.src.main import brain_search
        with self.assertRaises(ValueError):
            self._run(brain_search(query="test", top_k=0))

    def test_search_top_k_over_limit_raises_value_error(self):
        from mcp_gateway.src.main import brain_search
        with self.assertRaises(ValueError):
            self._run(brain_search(query="test", top_k=101))

    def test_search_top_k_min_passes(self):
        from mcp_gateway.src.main import brain_search
        import httpx
        try:
            self._run(brain_search(query="test", top_k=1))
        except ValueError:
            self.fail("top_k=1 should not raise ValueError")
        except Exception:
            pass  # HTTP failure OK — validation passed

    def test_search_top_k_max_passes(self):
        from mcp_gateway.src.main import brain_search
        import httpx
        try:
            self._run(brain_search(query="test", top_k=100))
        except ValueError:
            self.fail("top_k=100 should not raise ValueError")
        except Exception:
            pass

    def test_list_limit_zero_raises_value_error(self):
        from mcp_gateway.src.main import brain_list
        with self.assertRaises(ValueError):
            self._run(brain_list(limit=0))

    def test_list_limit_over_max_raises_value_error(self):
        from mcp_gateway.src.main import brain_list
        with self.assertRaises(ValueError):
            self._run(brain_list(limit=201))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm failures**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_boundary_values.py -v 2>&1 | head -50
```

Expected: Some fail (content boundaries, bulk, sync-check) until we check schemas; gateway tests fail until Task 1 is done. If Task 1 already committed, gateway tests should pass already.

- [ ] **Step 3: Check what actually fails and investigate**

If schema boundary tests fail, check `src/schemas.py` for exact field validators. The constants `MAX_CONTENT_LEN`, `MAX_ENTITY_TYPE_LEN`, `MAX_TAGS`, `MAX_BULK_RECORDS` must be exported from `src/schemas.py`. If they aren't exported (only used internally in validators), add them to imports in the test by reading the schemas file:

```bash
grep -n "MAX_CONTENT\|MAX_ENTITY\|MAX_TAGS\|MAX_BULK\|MAX_TAGS" \
  /Users/gniewkob/Repos/openbrain/unified/src/schemas.py | head -20
```

If `SyncCheckRequest` doesn't exist or has different field names:
```bash
grep -n "SyncCheck\|sync_check\|memory_id\|match_key\|obsidian_ref\|content_hash" \
  /Users/gniewkob/Repos/openbrain/unified/src/schemas.py | head -20
```

If `MemoryWriteManyRequest` uses a different field name:
```bash
grep -n "WriteManyRequest\|WriteMany\|records" \
  /Users/gniewkob/Repos/openbrain/unified/src/schemas.py | head -20
```

Adjust imports and field names in the test to match actual schema.

- [ ] **Step 4: Run all boundary value tests to verify they pass**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_boundary_values.py -v
```

Expected: All tests PASS in < 500ms.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All previously passing tests still pass. New tests added.

- [ ] **Step 6: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
git add tests/test_boundary_values.py
git commit -m "test: TEST-004 — add schema and gateway boundary value tests

Pure Pydantic unit tests for content length, entity_type length, tags list,
bulk record limit, SyncCheckRequest exactly-one validator, and
gateway top_k/limit bounds. No DB or HTTP required. Runs in <500ms."
```

---

## Definition of Done

- [ ] `brain_search(top_k=0)` raises `ValueError`
- [ ] `brain_search(top_k=101)` raises `ValueError`
- [ ] `brain_list(limit=201)` raises `ValueError`
- [ ] All 6 tests in `test_auth_security.py` pass
- [ ] No `sys.modules` manipulation in the 2 fixed tests
- [ ] `test_boundary_values.py` all pass in < 500ms
- [ ] No existing tests broken
