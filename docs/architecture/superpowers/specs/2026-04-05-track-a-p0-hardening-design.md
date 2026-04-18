# OpenBrain Track A — P0 Code Hardening Design

**Date:** 2026-04-05
**Status:** Approved
**Scope:** P0 code changes only (no data ops, no Track B)

---

## Overview

Five targeted improvements to bring OpenBrain to production-ready state on the code layer:

1. Secret scanning middleware
2. Contract tests (gateway ↔ backend schema parity)
3. E2E tests for `brain_update` invariants
4. `brain_capabilities` with real backend status
5. Error normalization (`ErrorDetail` envelope)

No migrations required. No breaking API changes. All changes are additive or wrapped transparently.

---

## 1. Secret Scanning Middleware

### Location
`unified/src/middleware.py` (new or extended) + registration in `unified/src/app_factory.py`

### Patterns scanned
- API keys: `sk-...`, `ghp_...`, `xoxb-...`, `AIza...`
- JWT tokens: 3-segment base64 (`xxxxx.xxxxx.xxxxx`)
- Inline credentials: `password=...`, `secret=...`, `api_key=...` in content
- Auth URLs: `https://user:pass@host`
- Private keys: `-----BEGIN ... PRIVATE KEY-----`

### Fields scanned
- `content` (string, always)
- `custom_fields` (recursive — all string values)

### Endpoints protected
- `POST /api/v1/memory/write`
- `POST /api/v1/memory/write-many`
- `PATCH /api/v1/memory/{id}`
- `POST /api/v1/memory/bulk-upsert`

Read-only endpoints (`GET`, `DELETE`, search, export) are not scanned.

### Behavior on detection
- Returns `400` with `ErrorDetail(code="secret_detected", message="...", retryable=False)`
- Logs the event with matched pattern name only — never logs the matched value
- Increments metric: `secret_scan_blocks_total`

### Invariants
- Scanning never mutates content
- False-positive rate acceptable: write operations are low-frequency
- Can be disabled per-environment with `DISABLE_SECRET_SCANNING=1` (for testing)

---

## 2. Contract Tests (gateway ↔ backend schema parity)

### Location
`unified/tests/test_contract_parity.py` (new file)

### Approach
Pure Pydantic unit tests — no DB, no HTTP, no mocks. Fast and deterministic.

For each tool:
1. Build the exact payload the gateway sends
2. Verify the backend schema accepts it without validation error
3. Verify the backend schema has no required fields the gateway doesn't provide

### Tools covered

| Tool | Gateway endpoint | Backend schema |
|------|-----------------|----------------|
| `brain_store` | `POST /write` | `MemoryWriteRequest` → `MemoryWriteRecord` |
| `brain_update` | `PATCH /{id}` | `MemoryUpdate` |
| `brain_upsert_bulk` | `POST /bulk-upsert` | `list[MemoryUpsertItem]` |
| `brain_store_bulk` | `POST /write-many` | `MemoryWriteManyRequest` |
| `brain_sync_check` | `POST /sync-check` | `SyncCheckRequest` |

### Definition of done
- No test can pass if gateway sends a field the backend schema doesn't accept
- No test can pass if backend requires a field the gateway doesn't send
- Tests run in < 1 second total (pure unit)

---

## 3. E2E Tests for `brain_update` Invariants

### Location
`unified/tests/test_update_e2e.py` (new file)

### Invariants verified

| Invariant | build/personal | corporate |
|-----------|---------------|-----------|
| `id` unchanged | ✓ same ID | ✗ new ID |
| `root_id` unchanged | ✓ | ✓ |
| `match_key` preserved | ✓ | ✓ |
| `owner` preserved if not provided | ✓ | ✓ |
| `version` | unchanged | +1 |
| old record `status` | `active` | `superseded` |
| new record `previous_id` | `None` | old `id` |
| old record `superseded_by` | `None` | new `id` |
| `content_hash` updated | ✓ | ✓ |

### Test cases
```
test_build_update_preserves_id_and_root_id
test_personal_update_preserves_id_and_root_id
test_corporate_update_creates_new_version_with_correct_lineage
test_update_preserves_match_key_when_not_provided
test_update_preserves_owner_when_not_provided
test_update_skips_when_content_unchanged
test_update_raises_404_for_missing_id
test_update_does_not_create_duplicate_without_match_key  [regression]
test_corporate_supersede_happens_before_insert          [regression]
```

### Implementation approach
`AsyncMock` + `patch` — no DB, no HTTP. Tests the `update_memory()` business logic layer directly. Does not duplicate `test_patch_endpoint.py` (which tests HTTP layer) or `test_update_memory.py` (which tests field preservation).

---

## 4. `brain_capabilities` with Real Backend Status

### Gateway change (`unified/mcp-gateway/src/main.py`)
Tool queries `GET /health` on the backend with 5s timeout before assembling response.

### Response shape
```json
{
  "platform": "OpenBrain V1 (Gateway)",
  "backend": {
    "status": "ok | unavailable",
    "url": "http://...",
    "db": "ok | degraded | unknown",
    "vector_store": "ok | degraded | unknown"
  },
  "obsidian_local": {
    "status": "enabled | disabled",
    "reason": null | "Set ENABLE_LOCAL_OBSIDIAN_TOOLS=1 to enable"
  },
  "tier_1_core": {"status": "stable", "tools": ["search", "get", "store", "update"]},
  "tier_2_advanced": {"status": "active", "tools": [...]},
  "tier_3_admin": {"status": "guarded", "tools": ["store_bulk", "upsert_bulk", "maintain"]}
}
```

### Backend `/health` extension (`unified/src/api/v1/health.py`)
Adds `db` and `vector_store` fields to the existing health response:
- `db`: result of `SELECT 1` via SQLAlchemy — `"ok"` or `"degraded"`
- `vector_store`: HTTP GET to Ollama embed endpoint — `"ok"` or `"degraded"`

### Obsidian tools behavior
Tools remain registered in MCP manifest (FastMCP cannot hide tools dynamically). When `ENABLE_LOCAL_OBSIDIAN_TOOLS=0`:
- `brain_capabilities` reports `obsidian_local.status = "disabled"` with reason
- Calling any obsidian tool returns existing `ValueError` with clear message
- Client can check capabilities before calling — no surprise runtime error

---

## 5. Error Normalization

### Location
`unified/src/app_factory.py` (global exception handlers)

### `ErrorDetail` envelope (schema already exists in `schemas.py`)
```json
{
  "error": {
    "code": "memory_not_found",
    "message": "Memory mem-123 does not exist",
    "details": {"memory_id": "mem-123"},
    "retryable": false
  }
}
```

### Error code map

| HTTP | code | trigger |
|------|------|---------|
| 400 | `secret_detected` | secret scanning block |
| 400 | `validation_error` | Pydantic / malformed input |
| 401 | `auth_required` | missing token |
| 403 | `access_denied` | domain/policy denial |
| 403 | `corporate_delete_forbidden` | delete on corporate memory |
| 404 | `memory_not_found` | missing record |
| 409 | `match_key_conflict` | create_only on existing match_key |
| 422 | `semantic_error` | sync_check without identifier, etc. |
| 503 | `backend_unavailable` | DB or Ollama down |

### Implementation
- Global `HTTPException` handler in `app_factory.py` wraps all `HTTPException` into `ErrorDetail` envelope
- `ValueError` from business logic → `422 semantic_error`
- Unhandled exceptions → `500 internal_error`, no stack trace in response body
- `retryable: true` only for `503`
- Existing `raise HTTPException(status_code=...)` calls unchanged — handler wraps transparently

---

## Files Changed

| File | Change |
|------|--------|
| `unified/src/middleware.py` | Add `SecretScanMiddleware` |
| `unified/src/app_factory.py` | Register middleware + global exception handlers |
| `unified/src/api/v1/health.py` | Add `db` + `vector_store` to health response |
| `unified/mcp-gateway/src/main.py` | Extend `brain_capabilities` to query `/health` |
| `unified/tests/test_contract_parity.py` | New: contract parity tests |
| `unified/tests/test_update_e2e.py` | New: update invariant E2E tests |

Total: 4 files modified, 2 new test files.

---

## Definition of Done

- [ ] Secret scanning blocks writes containing plaintext secrets
- [ ] Secret scanning never logs the matched value
- [ ] All contract tests pass without DB or HTTP
- [ ] All `brain_update` invariant tests pass
- [ ] `brain_capabilities` shows real backend/db/vector_store status
- [ ] `brain_capabilities` shows Obsidian enabled/disabled with reason
- [ ] All 4xx/5xx responses use `ErrorDetail` envelope
- [ ] `retryable` field present on all error responses
- [ ] No existing tests broken
