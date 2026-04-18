# OpenBrain Track B — P1 Security & Performance Fixes Design

**Date:** 2026-04-05
**Status:** Approved
**Scope:** Three targeted fixes: gateway parameter validation, auth test repair, boundary value tests

---

## Overview

Three focused improvements from the P1 audit backlog that are safe, small, and high ROI:

1. **PERF-007** — Input validation for `top_k`/`limit` parameters in MCP gateway
2. **TEST-002** — Fix 2 failing tests in `test_auth_security.py` (remove `sys.modules` hack)
3. **TEST-004** — Boundary value tests for schema limits and gateway parameters

No migrations required. No breaking API changes. All changes are additive or fix broken behavior.

---

## 1. PERF-007 — Gateway Parameter Validation

### Location
`unified/mcp-gateway/src/main.py`

### Problem
Three gateway tools accept unbounded integer parameters:
- `brain_search`: `top_k: int = 5` — no upper bound
- `brain_list`: `limit: int = 20` — no upper bound
- `brain_obsidian_sync` (and related): `limit: int = 50` — no upper bound

A caller can send `top_k=99999`, causing backend overload.

### Constants (module-level)
```python
MAX_SEARCH_TOP_K = 100
MAX_LIST_LIMIT = 200
MAX_SYNC_LIMIT = 200
```

### Validation pattern
Add at the entry of each affected tool:
```python
if not 1 <= top_k <= MAX_SEARCH_TOP_K:
    raise ValueError(f"top_k must be 1–{MAX_SEARCH_TOP_K}, got {top_k}")
```

`ValueError` is caught by the P0 `value_error_handler` → `422 semantic_error` with a clear message.

### Tools affected
| Tool | Parameter | Min | Max |
|------|-----------|-----|-----|
| `brain_search` | `top_k` | 1 | 100 |
| `brain_list` | `limit` | 1 | 200 |
| `brain_obsidian_sync` | `limit` | 1 | 200 |
| `brain_obsidian_collection` | `limit` | 1 | 200 |

### Tests
New file: `unified/tests/test_gateway_validation.py`
- `test_search_top_k_zero_raises`
- `test_search_top_k_over_limit_raises`
- `test_search_top_k_boundary_values_pass` (1 and 100)
- `test_list_limit_over_max_raises`
- `test_list_limit_boundary_values_pass`

Tests call the validation logic directly (no HTTP, no DB).

---

## 2. TEST-002 — Fix `test_auth_security.py`

### Location
`unified/tests/test_auth_security.py`

### Problem
Two tests fail because `_reload_auth()` reimports `src.auth`, but `PUBLIC_MODE`, `PUBLIC_BASE_URL`, and `OIDC_ISSUER_URL` are read as module-level globals at first import (lines 29–31). A subsequent reload with `patch.dict(os.environ, ...)` doesn't update the already-frozen globals that `validate_security_configuration()` reads.

Failing tests:
- `test_public_mode_requires_oidc_issuer`
- `test_public_base_url_requires_oidc_issuer`

### Fix
Remove `_reload_auth()` and the entire `sys.modules` hack. Instead, patch the module-level globals in `src.auth` directly and call `validate_security_configuration()`:

```python
def test_public_mode_requires_oidc_issuer(self):
    from src.auth import validate_security_configuration
    with patch("src.auth.PUBLIC_EXPOSURE", True), \
         patch("src.auth.OIDC_ISSUER_URL", ""), \
         patch("src.auth.INTERNAL_API_KEY", "super-secret"), \
         patch("src.auth.DEV_DEFAULT_INTERNAL_KEY", "openbrain-local-dev"):
        with self.assertRaisesRegex(RuntimeError, "requires OIDC_ISSUER_URL"):
            validate_security_configuration()
```

### Invariants
- No changes to production code (`src/auth.py` untouched)
- All 6 tests in `test_auth_security.py` must pass after fix
- No `sys.modules` manipulation remains in the file

---

## 3. TEST-004 — Boundary Value Tests

### Location
`unified/tests/test_boundary_values.py` (new file)

### Approach
Pure Pydantic unit tests — no DB, no HTTP. Fast and deterministic.

### Coverage

#### Schema field limits
| Field | Test |
|-------|------|
| `content` empty string | → `ValidationError` |
| `content` at max length (20 000 chars) | → OK |
| `content` over max length (20 001 chars) | → `ValidationError` |
| `tags` list at max (20 items) | → OK |
| `tags` list over max (21 items) | → `ValidationError` |
| `entity_type` at 64 chars | → OK |
| `entity_type` at 65 chars | → `ValidationError` |
| `domain` unknown value | → `ValidationError` |

#### Bulk limits
| Test | Expected |
|------|----------|
| `MemoryWriteManyRequest` with 100 records | → OK |
| `MemoryWriteManyRequest` with 101 records | → `ValidationError` |

#### `SyncCheckRequest` validator
| Test | Expected |
|------|----------|
| All identifiers `None` | → `ValidationError` |
| Two identifiers provided | → `ValidationError` |
| Exactly one identifier | → OK |

#### Gateway parameter bounds (after PERF-007)
| Test | Expected |
|------|----------|
| `top_k=0` | → `ValueError` |
| `top_k=101` | → `ValueError` |
| `top_k=1` | → OK |
| `top_k=100` | → OK |
| `limit=0` | → `ValueError` |
| `limit=201` | → `ValueError` |

### Definition of done
- All boundary tests pass in < 500ms
- No DB, no HTTP required

---

## Files Changed

| File | Change |
|------|--------|
| `unified/mcp-gateway/src/main.py` | Add `MAX_*` constants + `ValueError` guards in 4 tools |
| `unified/tests/test_auth_security.py` | Replace `sys.modules` hack with direct `patch` of module globals |
| `unified/tests/test_gateway_validation.py` | New: gateway parameter validation tests |
| `unified/tests/test_boundary_values.py` | New: schema and gateway boundary value tests |

Total: 2 files modified, 2 new test files.

---

## Definition of Done

- [ ] `brain_search(top_k=0)` raises `ValueError`
- [ ] `brain_search(top_k=101)` raises `ValueError`
- [ ] `brain_list(limit=201)` raises `ValueError`
- [ ] All 6 tests in `test_auth_security.py` pass
- [ ] No `sys.modules` manipulation in test suite
- [ ] Content length boundary validated at schema level
- [ ] Bulk record limit validated at schema level
- [ ] No existing tests broken
