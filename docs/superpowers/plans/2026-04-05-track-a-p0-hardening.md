# OpenBrain Track A — P0 Code Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden OpenBrain with secret scanning, contract tests, update invariant tests, real capability status, and normalized error envelopes.

**Architecture:** Secret scanning lives in FastAPI middleware (intercepts before any route logic). Error normalization extends the existing `exceptions.py` handler to cover `HTTPException` and add `retryable` field. Contract tests are pure Pydantic unit tests. Gateway `brain_capabilities` queries `/readyz` for live status.

**Tech Stack:** Python 3.13, FastAPI, Starlette `BaseHTTPMiddleware`, Pydantic v2, pytest, httpx, unittest.mock

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `unified/src/middleware.py` | **Modify** | Add `SecretScanMiddleware` class + `_scan_for_secrets()` |
| `unified/src/app_factory.py` | **Modify** | Register `SecretScanMiddleware` after `SecurityHeadersMiddleware` |
| `unified/src/exceptions.py` | **Modify** | Add `SecretDetectedError`, `HTTPException` handler, `retryable` field |
| `unified/src/schemas.py` | **Modify** | Add `retryable: bool = False` to `ErrorDetail` |
| `unified/src/api/v1/health.py` | **Modify** | Extend `/readyz` with `vector_store` Ollama check |
| `unified/mcp-gateway/src/main.py` | **Modify** | Extend `brain_capabilities` to call `/readyz` |
| `unified/tests/test_secret_scan.py` | **Create** | Unit + integration tests for secret scanning |
| `unified/tests/test_contract_parity.py` | **Create** | Gateway ↔ backend schema parity tests |
| `unified/tests/test_update_e2e.py` | **Create** | `brain_update` invariant E2E tests |
| `unified/tests/test_error_normalization.py` | **Create** | Error envelope + retryable field tests |

---

## Task 1: Secret Scanner — write failing tests

**Files:**
- Create: `unified/tests/test_secret_scan.py`

- [ ] **Step 1.1: Create the test file**

```python
# unified/tests/test_secret_scan.py
"""Tests for secret scanning middleware and scanner logic."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests: _scan_for_secrets()
# ---------------------------------------------------------------------------

class TestScanForSecrets:
    """Unit tests for the scanner function (no HTTP, no app)."""

    def _scan(self, data: dict):
        from src.middleware import _scan_for_secrets
        return _scan_for_secrets(data)

    def test_clean_content_returns_false(self):
        found, pattern = self._scan({"content": "This is a normal memory about projects."})
        assert found is False
        assert pattern is None

    def test_openai_key_in_content_detected(self):
        found, pattern = self._scan({"content": "my key is sk-abcdefghijklmnopqrstuvwxyz1234"})
        assert found is True
        assert pattern == "openai_api_key"

    def test_github_token_in_content_detected(self):
        found, pattern = self._scan({"content": "token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"})
        assert found is True
        assert pattern == "github_token"

    def test_jwt_token_in_content_detected(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        found, pattern = self._scan({"content": f"Authorization header was: {jwt}"})
        assert found is True
        assert pattern == "jwt_token"

    def test_pem_private_key_in_content_detected(self):
        found, pattern = self._scan({"content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."})
        assert found is True
        assert pattern == "pem_private_key"

    def test_auth_url_in_content_detected(self):
        found, pattern = self._scan({"content": "connect to https://admin:password123@db.example.com"})
        assert found is True
        assert pattern == "auth_url"

    def test_inline_api_key_credential_detected(self):
        found, pattern = self._scan({"content": "api_key=supersecretvalue123"})
        assert found is True
        assert pattern == "inline_credential"

    def test_secret_in_custom_fields_detected(self):
        found, pattern = self._scan({
            "content": "normal content",
            "custom_fields": {"config": "password=hunter2secret"}
        })
        assert found is True
        assert pattern == "inline_credential"

    def test_nested_custom_fields_scanned(self):
        found, pattern = self._scan({
            "content": "normal",
            "custom_fields": {"level1": {"level2": "sk-abcdefghijklmnopqrstuvwxyz1234"}}
        })
        assert found is True
        assert pattern == "openai_api_key"

    def test_missing_content_key_is_safe(self):
        """Payloads without 'content' key must not crash the scanner."""
        found, pattern = self._scan({"title": "just a title"})
        assert found is False

    def test_non_string_values_skipped(self):
        found, pattern = self._scan({
            "content": "normal",
            "custom_fields": {"count": 42, "enabled": True, "items": [1, 2, 3]}
        })
        assert found is False


# ---------------------------------------------------------------------------
# Integration tests: middleware blocks write endpoints
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_app():
    """Minimal FastAPI app with SecretScanMiddleware for integration tests."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from src.middleware import SecretScanMiddleware

    app = FastAPI()
    app.add_middleware(SecretScanMiddleware)

    @app.post("/api/v1/memory/write")
    async def write_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/memory/write-many")
    async def write_many_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.patch("/api/v1/memory/{memory_id}")
    async def patch_endpoint(memory_id: str, request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/memory/bulk-upsert")
    async def bulk_upsert_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.get("/api/v1/memory/search")
    async def search_endpoint():
        return JSONResponse({"results": []})

    return app


@pytest.fixture()
def client(test_app):
    from httpx import ASGITransport, AsyncClient
    import asyncio
    # Return sync wrapper compatible with pytest
    return test_app


class TestSecretScanMiddlewareIntegration:

    def _post(self, app, path: str, body: dict):
        """Synchronous helper using AsyncClient."""
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                return await c.post(path, json=body)

        return asyncio.get_event_loop().run_until_complete(_run())

    def _patch(self, app, path: str, body: dict):
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                return await c.patch(path, json=body)

        return asyncio.get_event_loop().run_until_complete(_run())

    def _get(self, app, path: str):
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                return await c.get(path)

        return asyncio.get_event_loop().run_until_complete(_run())

    def test_clean_write_passes_through(self, test_app):
        r = self._post(test_app, "/api/v1/memory/write", {"content": "normal content"})
        assert r.status_code == 200

    def test_secret_in_write_blocked_with_400(self, test_app):
        r = self._post(test_app, "/api/v1/memory/write",
                       {"content": "sk-abcdefghijklmnopqrstuvwxyz1234"})
        assert r.status_code == 400

    def test_blocked_response_has_error_envelope(self, test_app):
        r = self._post(test_app, "/api/v1/memory/write",
                       {"content": "sk-abcdefghijklmnopqrstuvwxyz1234"})
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == "secret_detected"
        assert body["error"]["retryable"] is False

    def test_secret_in_write_many_blocked(self, test_app):
        r = self._post(test_app, "/api/v1/memory/write-many",
                       {"records": [{"content": "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"}]})
        assert r.status_code == 400

    def test_secret_in_patch_blocked(self, test_app):
        r = self._patch(test_app, "/api/v1/memory/mem-123",
                        {"content": "-----BEGIN RSA PRIVATE KEY-----\ndata"})
        assert r.status_code == 400

    def test_secret_in_bulk_upsert_blocked(self, test_app):
        r = self._post(test_app, "/api/v1/memory/bulk-upsert",
                       [{"content": "normal"}, {"content": "api_key=supersecretvalue123"}])
        assert r.status_code == 400

    def test_get_endpoint_not_scanned(self, test_app):
        """GET requests must never be blocked by the scanner."""
        r = self._get(test_app, "/api/v1/memory/search")
        assert r.status_code == 200

    def test_non_json_body_passes_through(self, test_app):
        """Non-parseable bodies must not crash the middleware."""
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
                return await c.post(
                    "/api/v1/memory/write",
                    content=b"not json at all",
                    headers={"content-type": "application/json"},
                )

        r = asyncio.get_event_loop().run_until_complete(_run())
        # Middleware must not return 400 for parse errors — let FastAPI handle it
        assert r.status_code != 400 or r.json().get("error", {}).get("code") != "secret_detected"
```

- [ ] **Step 1.2: Run the tests — verify they all FAIL with ImportError**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_secret_scan.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name '_scan_for_secrets' from 'src.middleware'`

- [ ] **Step 1.3: Commit failing tests**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/tests/test_secret_scan.py
git commit -m "test(security): add failing secret scan tests"
```

---

## Task 2: Secret Scanner — implement `_scan_for_secrets` and `SecretScanMiddleware`

**Files:**
- Modify: `unified/src/middleware.py`

- [ ] **Step 2.1: Add scanner logic and middleware to `middleware.py`**

Open `unified/src/middleware.py` and **append** the following (keep existing `SecurityHeadersMiddleware` intact):

```python
# ---------------------------------------------------------------------------
# Secret Scanning
# ---------------------------------------------------------------------------

import json
import logging
import os
import re
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_secret_log = logging.getLogger("openbrain.security.secret_scan")

# Paths that accept content bodies and must be scanned
_WRITE_PATHS: frozenset[str] = frozenset(
    [
        "/api/v1/memory/write",
        "/api/v1/memory/write-many",
        "/api/v1/memory/bulk-upsert",
    ]
)
# PATCH /api/v1/memory/{id} matched by prefix
_PATCH_PREFIX = "/api/v1/memory/"

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai_api_key"),
    (re.compile(r"gh[ps]_[A-Za-z0-9]{36,}"), "github_token"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "slack_token"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "google_api_key"),
    # JWT: three base64url segments starting with eyJ
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{20,}"), "jwt_token"),
    # Auth URLs with embedded credentials
    (re.compile(r"https?://[^:@\s/]+:[^@\s/]{4,}@[^\s]+"), "auth_url"),
    # PEM private keys
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "pem_private_key"),
    # Generic inline credentials (conservative — requires 8+ char value)
    (
        re.compile(
            r"(?i)\b(password|api_key|apikey|secret_key)\s*[:=]\s*[\"']?[^\s\"']{8,}"
        ),
        "inline_credential",
    ),
]

_DISABLE_SECRET_SCANNING = os.environ.get("DISABLE_SECRET_SCANNING", "").lower() in {
    "1", "true", "yes"
}


def _scan_string(value: str) -> tuple[bool, str | None]:
    """Scan a single string value against all secret patterns."""
    for pattern, name in _SECRET_PATTERNS:
        if pattern.search(value):
            return True, name
    return False, None


def _scan_for_secrets(data: Any) -> tuple[bool, str | None]:
    """
    Recursively scan a parsed JSON structure for secret patterns.

    Scans:
    - Top-level 'content' string
    - All string values inside 'custom_fields' (recursively)

    Returns:
        (True, pattern_name) if a secret is found
        (False, None) if clean
    """
    if not isinstance(data, (dict, list)):
        return False, None

    # Handle list (e.g. bulk-upsert body)
    if isinstance(data, list):
        for item in data:
            found, pattern = _scan_for_secrets(item)
            if found:
                return True, pattern
        return False, None

    # Scan 'content' field
    content = data.get("content")
    if isinstance(content, str):
        found, pattern = _scan_string(content)
        if found:
            return True, pattern

    # Scan 'custom_fields' recursively
    custom_fields = data.get("custom_fields")
    if isinstance(custom_fields, dict):
        found, pattern = _scan_dict_values(custom_fields)
        if found:
            return True, pattern

    # Scan nested 'records' (write-many)
    records = data.get("records")
    if isinstance(records, list):
        for record in records:
            found, pattern = _scan_for_secrets(record)
            if found:
                return True, pattern

    # Scan nested 'record' (single write)
    record = data.get("record")
    if isinstance(record, dict):
        found, pattern = _scan_for_secrets(record)
        if found:
            return True, pattern

    return False, None


def _scan_dict_values(d: dict) -> tuple[bool, str | None]:
    """Recursively scan all string values in a dict."""
    for value in d.values():
        if isinstance(value, str):
            found, pattern = _scan_string(value)
            if found:
                return True, pattern
        elif isinstance(value, dict):
            found, pattern = _scan_dict_values(value)
            if found:
                return True, pattern
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    found, pattern = _scan_string(item)
                    if found:
                        return True, pattern
    return False, None


def _is_write_path(method: str, path: str) -> bool:
    """Return True if this request targets a write endpoint that must be scanned."""
    if method == "POST" and path in _WRITE_PATHS:
        return True
    if method == "PATCH" and path.startswith(_PATCH_PREFIX):
        return True
    return False


class SecretScanMiddleware(BaseHTTPMiddleware):
    """
    Intercepts write requests and blocks those containing plaintext secrets.

    Scans 'content' and 'custom_fields' in the request body.
    Returns 400 with ErrorDetail(code='secret_detected') if a secret pattern matches.

    Disable for tests with DISABLE_SECRET_SCANNING=1.
    """

    async def dispatch(self, request: Request, call_next):
        if _DISABLE_SECRET_SCANNING:
            return await call_next(request)

        if not _is_write_path(request.method, request.url.path):
            return await call_next(request)

        # Read and cache body (Starlette caches in request._body — safe for downstream)
        try:
            raw = await request.body()
            data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            # Unparseable body — let FastAPI's validation handle it
            return await call_next(request)

        found, pattern_name = _scan_for_secrets(data)
        if found:
            _secret_log.warning(
                "secret_scan_blocked",
                path=request.url.path,
                method=request.method,
                pattern=pattern_name,
                # Never log the matched value — only the pattern name
            )
            # Import here to avoid circular imports at module load
            from .telemetry import incr_metric
            incr_metric("secret_scan_blocks_total")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "secret_detected",
                        "message": (
                            f"Request blocked: potential secret detected "
                            f"(pattern: {pattern_name}). "
                            "Store secret references, not plaintext secrets."
                        ),
                        "details": {"pattern": pattern_name},
                        "retryable": False,
                    }
                },
            )

        return await call_next(request)
```

- [ ] **Step 2.2: Run the unit tests — they should now pass**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_secret_scan.py::TestScanForSecrets -v
```

Expected: all `TestScanForSecrets` tests PASS.

- [ ] **Step 2.3: Run the integration tests**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_secret_scan.py::TestSecretScanMiddlewareIntegration -v
```

Expected: all integration tests PASS.

- [ ] **Step 2.4: Commit implementation**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/src/middleware.py
git commit -m "feat(security): implement SecretScanMiddleware with pattern-based detection"
```

---

## Task 3: Register `SecretScanMiddleware` in the production app

**Files:**
- Modify: `unified/src/app_factory.py`

- [ ] **Step 3.1: Add import and registration**

In `unified/src/app_factory.py`, add the import after existing imports:

```python
from .middleware import SecretScanMiddleware
```

Then inside `create_app()`, after `app.add_middleware(SecurityHeadersMiddleware)`, add:

```python
    # Secret scanning — blocks writes containing plaintext secrets
    app.add_middleware(SecretScanMiddleware)
```

The final middleware block in `create_app()` should look like:

```python
    # Security headers on every response (added after CORS — runs first in ASGI stack)
    app.add_middleware(SecurityHeadersMiddleware)

    # Secret scanning — blocks writes containing plaintext secrets
    app.add_middleware(SecretScanMiddleware)

    # Register centralized exception handlers
    register_exception_handlers(app)

    return app
```

- [ ] **Step 3.2: Run full existing test suite to verify nothing is broken**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v --ignore=tests/test_api_endpoints_live.py --ignore=tests/validate_openbrain_api.py -x 2>&1 | tail -30
```

Expected: all existing tests PASS (secret scan tests added in Task 1 also pass).

- [ ] **Step 3.3: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/src/app_factory.py
git commit -m "feat(security): register SecretScanMiddleware in production app"
```

---

## Task 4: Contract Parity Tests

**Files:**
- Create: `unified/tests/test_contract_parity.py`

- [ ] **Step 4.1: Create the test file**

```python
# unified/tests/test_contract_parity.py
"""
Contract parity tests: verify gateway payload ↔ backend schema alignment.

No mocks, no DB, no HTTP. Pure Pydantic unit tests.
Each test verifies:
1. The exact payload the gateway sends is accepted by the backend schema.
2. The backend schema has no required fields the gateway doesn't provide.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestBrainStoreContract:
    """brain_store → POST /api/v1/memory/write → MemoryWriteRequest."""

    def test_minimal_gateway_payload_accepted(self):
        """Gateway sends only content + domain + entity_type in the record."""
        from src.schemas import MemoryWriteRecord, MemoryWriteRequest

        record = MemoryWriteRecord(
            content="test content",
            domain="build",
            entity_type="Note",
        )
        req = MemoryWriteRequest(record=record, write_mode="upsert")
        assert req.record.content == "test content"

    def test_full_gateway_payload_accepted(self):
        """All optional fields the gateway may send are accepted."""
        from src.schemas import MemoryWriteRecord, MemoryWriteRequest

        record = MemoryWriteRecord(
            content="test content",
            domain="corporate",
            entity_type="Decision",
            title="My Decision",
            sensitivity="confidential",
            owner="alice",
            tenant_id="tenant-1",
            tags=["eng", "auth"],
            custom_fields={"priority": "high"},
            obsidian_ref="vault/note.md",
            match_key="corp:decision:abc",
        )
        req = MemoryWriteRequest(record=record, write_mode="upsert")
        assert req.record.match_key == "corp:decision:abc"

    def test_no_required_fields_without_defaults_in_record(self):
        """MemoryWriteRecord must have no required fields the gateway omits."""
        from src.schemas import MemoryWriteRecord
        import inspect

        # Fields the gateway always provides
        gateway_provides = {"content", "domain"}

        required_fields = [
            name
            for name, field in MemoryWriteRecord.model_fields.items()
            if field.is_required() and name not in gateway_provides
        ]
        assert required_fields == [], (
            f"MemoryWriteRecord has required fields the gateway doesn't provide: "
            f"{required_fields}"
        )


class TestBrainUpdateContract:
    """brain_update → PATCH /api/v1/memory/{id} → MemoryUpdate."""

    def test_minimal_gateway_payload_accepted(self):
        """Gateway always sends content + updated_by."""
        from src.schemas import MemoryUpdate

        data = MemoryUpdate(content="new content", updated_by="agent")
        assert data.content == "new content"

    def test_gateway_payload_with_all_optional_fields(self):
        """All fields the gateway may optionally send are accepted."""
        from src.schemas import MemoryUpdate

        data = MemoryUpdate(
            content="new content",
            title="New Title",
            updated_by="agent",
            sensitivity="internal",
            owner="bob",
            tenant_id="tenant-1",
            tags=["updated"],
            custom_fields={"key": "value"},
            obsidian_ref="vault/note.md",
        )
        assert data.title == "New Title"

    def test_no_required_fields_in_memory_update(self):
        """MemoryUpdate must have no required fields — all are optional."""
        from src.schemas import MemoryUpdate

        required_fields = [
            name
            for name, field in MemoryUpdate.model_fields.items()
            if field.is_required()
        ]
        assert required_fields == [], (
            f"MemoryUpdate has required fields: {required_fields}. "
            "This means brain_update cannot call PATCH without providing them."
        )

    def test_empty_payload_accepted(self):
        """Gateway must be able to send just updated_by."""
        from src.schemas import MemoryUpdate

        data = MemoryUpdate(updated_by="agent")
        assert data.content is None


class TestBrainUpsertBulkContract:
    """brain_upsert_bulk → POST /api/v1/memory/bulk-upsert → list[MemoryUpsertItem]."""

    def test_minimal_item_accepted(self):
        """Minimal item must be accepted — only content + domain + match_key."""
        from src.schemas import MemoryUpsertItem

        item = MemoryUpsertItem(
            content="test",
            domain="build",
            match_key="build:test:1",
        )
        assert item.match_key == "build:test:1"

    def test_no_required_fields_besides_content_and_domain(self):
        """Only content and domain should be required in MemoryUpsertItem."""
        from src.schemas import MemoryUpsertItem

        required = [
            name
            for name, field in MemoryUpsertItem.model_fields.items()
            if field.is_required()
        ]
        # match_key is NOT required in schema (required at business logic level)
        assert set(required) <= {"content", "domain"}, (
            f"MemoryUpsertItem has unexpected required fields: {required}"
        )


class TestBrainStoreBulkContract:
    """brain_store_bulk → POST /api/v1/memory/write-many → MemoryWriteManyRequest."""

    def test_minimal_payload_accepted(self):
        from src.schemas import MemoryWriteManyRequest, MemoryWriteRecord

        record = MemoryWriteRecord(content="bulk item", domain="build")
        req = MemoryWriteManyRequest(records=[record], write_mode="upsert")
        assert len(req.records) == 1

    def test_items_list_is_required(self):
        """write-many requires at least the records list."""
        from src.schemas import MemoryWriteManyRequest

        with pytest.raises(ValidationError):
            MemoryWriteManyRequest()  # missing records


class TestBrainSyncCheckContract:
    """brain_sync_check → POST /api/v1/memory/sync-check → SyncCheckRequest."""

    def test_memory_id_only_accepted(self):
        from src.schemas import SyncCheckRequest

        req = SyncCheckRequest(memory_id="mem-123")
        assert req.memory_id == "mem-123"

    def test_match_key_only_accepted(self):
        from src.schemas import SyncCheckRequest

        req = SyncCheckRequest(match_key="build:test:1")
        assert req.match_key == "build:test:1"

    def test_obsidian_ref_only_accepted(self):
        from src.schemas import SyncCheckRequest

        req = SyncCheckRequest(obsidian_ref="vault/note.md")
        assert req.obsidian_ref == "vault/note.md"

    def test_multiple_identifiers_rejected(self):
        """Exactly one identifier must be provided."""
        from src.schemas import SyncCheckRequest

        with pytest.raises(ValidationError):
            SyncCheckRequest(memory_id="mem-123", match_key="mk:1")

    def test_no_identifiers_rejected(self):
        from src.schemas import SyncCheckRequest

        with pytest.raises(ValidationError):
            SyncCheckRequest()

    def test_file_hash_optional_with_memory_id(self):
        """file_hash is optional — existence check works without it."""
        from src.schemas import SyncCheckRequest

        req = SyncCheckRequest(memory_id="mem-123", file_hash="sha256abc")
        assert req.file_hash == "sha256abc"
```

- [ ] **Step 4.2: Run — all contract tests should PASS immediately**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_contract_parity.py -v
```

Expected: all PASS (contracts already aligned). If any FAIL, there is actual schema drift — fix the underlying schema before continuing.

- [ ] **Step 4.3: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/tests/test_contract_parity.py
git commit -m "test(contracts): add gateway↔backend schema parity tests"
```

---

## Task 5: `brain_update` E2E Invariant Tests

**Files:**
- Create: `unified/tests/test_update_e2e.py`

- [ ] **Step 5.1: Create the test file**

```python
# unified/tests/test_update_e2e.py
"""
E2E invariant tests for brain_update / update_memory().

Tests the business logic layer (update_memory in memory_writes.py) directly.
No DB, no HTTP. Uses AsyncMock + patch.

Invariants verified:
- build/personal: same id, same root_id, match_key preserved, owner preserved
- corporate: new id, root_id unchanged, previous_id = old id, superseded_by set
- version incremented for corporate, unchanged for build/personal
- content_hash updated on actual change
- skipped when content unchanged
- 404 behavior on missing id
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.models import DomainEnum, Memory
from src.schemas import (
    GovernanceMetadata,
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    MemoryUpdate,
    MemoryWriteResponse,
    SourceMetadata,
)


def _make_memory(
    *,
    mem_id: str = "mem-1",
    domain: DomainEnum = DomainEnum.build,
    entity_type: str = "Note",
    content: str = "original content",
    version: int = 1,
    owner: str = "alice",
    match_key: str = "build:note:1",
    root_id: str = "mem-1",
    content_hash: str = "hash-original",
) -> Memory:
    now = datetime.now(timezone.utc)
    return Memory(
        id=mem_id,
        domain=domain,
        entity_type=entity_type,
        content=content,
        embedding=None,
        owner=owner,
        created_by="tester",
        status="active",
        version=version,
        sensitivity="internal",
        superseded_by=None,
        tags=["tag1"],
        relations={"related": []},
        metadata_={
            "title": "Test Title",
            "custom_fields": {"priority": "low"},
            "root_id": root_id,
            "updated_by": "tester",
        },
        obsidian_ref=None,
        content_hash=content_hash,
        match_key=match_key,
        valid_from=None,
        created_at=now,
        updated_at=now,
    )


def _make_memory_out(memory: Memory, *, override_id: str | None = None) -> MemoryOut:
    now = datetime.now(timezone.utc)
    return MemoryOut(
        id=override_id or memory.id,
        domain=memory.domain.value,
        entity_type=memory.entity_type,
        content=memory.content,
        owner=memory.owner,
        status="active",
        version=memory.version,
        sensitivity="internal",
        superseded_by=None,
        tags=memory.tags or [],
        relations=memory.relations or {},
        obsidian_ref=None,
        custom_fields={},
        content_hash=memory.content_hash,
        match_key=memory.match_key,
        previous_id=None,
        root_id=memory.id,
        valid_from=None,
        created_at=now,
        updated_at=now,
        created_by="tester",
    )


def _make_memory_record(out: MemoryOut) -> MemoryRecord:
    return MemoryRecord(
        id=out.id,
        match_key=out.match_key,
        domain=out.domain,
        entity_type=out.entity_type,
        content=out.content,
        owner=out.owner,
        tags=out.tags,
        relations=MemoryRelations(),
        status=out.status,
        sensitivity=out.sensitivity,
        source=SourceMetadata(),
        governance=GovernanceMetadata(),
        obsidian_ref=None,
        custom_fields=out.custom_fields,
        content_hash=out.content_hash,
        version=out.version,
        previous_id=out.previous_id,
        root_id=out.root_id,
        superseded_by=None,
        valid_from=None,
        created_at=out.created_at,
        updated_at=out.updated_at,
        created_by=out.created_by,
        updated_by="agent",
    )


class TestBuildUpdateInvariants(unittest.IsolatedAsyncioTestCase):
    """build domain: update must be in-place, same id, same root_id."""

    async def test_build_update_preserves_id(self):
        from src import crud, memory_writes

        existing = _make_memory(mem_id="build-1", domain=DomainEnum.build)
        updated_out = _make_memory_out(existing)
        updated_out = updated_out.model_copy(update={"content": "updated content"})
        updated_record = _make_memory_record(updated_out)

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )

        with (
            patch.object(
                memory_writes,
                "handle_memory_write",
                new=AsyncMock(
                    return_value=MemoryWriteResponse(
                        status="updated", record=updated_record
                    )
                ),
            ),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=updated_out),
            ),
        ):
            result = await crud.update_memory(
                session, "build-1", MemoryUpdate(content="updated content"), actor="agent"
            )

        self.assertEqual(result.id, "build-1")

    async def test_build_update_preserves_root_id(self):
        from src import crud, memory_writes

        existing = _make_memory(mem_id="build-1", root_id="build-1")
        updated_out = _make_memory_out(existing)
        updated_record = _make_memory_record(updated_out)

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )

        with (
            patch.object(
                memory_writes,
                "handle_memory_write",
                new=AsyncMock(
                    return_value=MemoryWriteResponse(
                        status="updated", record=updated_record
                    )
                ),
            ),
            patch.object(
                memory_writes, "get_memory", new=AsyncMock(return_value=updated_out)
            ),
        ):
            result = await crud.update_memory(
                session, "build-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertEqual(result.root_id, "build-1")

    async def test_build_update_preserves_match_key(self):
        from src import crud, memory_writes

        existing = _make_memory(mem_id="build-1", match_key="build:note:1")
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        captured_request = {}

        async def capture_write(session, request, *, actor="agent", _commit=True):
            captured_request["req"] = request
            out = _make_memory_out(existing)
            record = _make_memory_record(out)
            return MemoryWriteResponse(status="updated", record=record)

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            await crud.update_memory(
                session, "build-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertEqual(captured_request["req"].record.match_key, "build:note:1")

    async def test_build_update_preserves_owner_when_not_provided(self):
        from src import crud, memory_writes

        existing = _make_memory(owner="alice")
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        captured_request = {}

        async def capture_write(session, request, *, actor="agent", _commit=True):
            captured_request["req"] = request
            out = _make_memory_out(existing)
            return MemoryWriteResponse(status="updated", record=_make_memory_record(out))

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            # Do NOT pass owner in MemoryUpdate
            await crud.update_memory(
                session, "mem-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertEqual(captured_request["req"].record.owner, "alice")

    async def test_build_update_uses_upsert_write_mode(self):
        from src import crud, memory_writes

        existing = _make_memory(domain=DomainEnum.build)
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        captured_request = {}

        async def capture_write(session, request, *, actor="agent", _commit=True):
            captured_request["req"] = request
            out = _make_memory_out(existing)
            return MemoryWriteResponse(status="updated", record=_make_memory_record(out))

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            await crud.update_memory(
                session, "mem-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertEqual(captured_request["req"].write_mode.value, "upsert")

    async def test_build_update_skipped_when_content_unchanged(self):
        from src import crud, memory_writes

        existing = _make_memory()
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )

        with (
            patch.object(
                memory_writes,
                "handle_memory_write",
                new=AsyncMock(
                    return_value=MemoryWriteResponse(status="skipped", record=None)
                ),
            ),
        ):
            result = await crud.update_memory(
                session,
                "mem-1",
                MemoryUpdate(content="original content"),
                actor="agent",
            )

        # skipped returns the existing memory unchanged (not None)
        # update_memory returns _to_out(memory) when write is skipped
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "mem-1")


class TestCorporateUpdateInvariants(unittest.IsolatedAsyncioTestCase):
    """corporate domain: update must create new version, preserve lineage."""

    async def test_corporate_update_creates_new_version(self):
        from src import crud, memory_writes

        existing = _make_memory(
            mem_id="corp-1",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            match_key="corp:decision:1",
            root_id="corp-1",
            version=1,
        )

        now = datetime.now(timezone.utc)
        versioned_out = MemoryOut(
            id="corp-2",
            domain="corporate",
            entity_type="Decision",
            content="updated content",
            owner="alice",
            status="active",
            version=2,
            sensitivity="internal",
            superseded_by=None,
            tags=["tag1"],
            relations={},
            obsidian_ref=None,
            custom_fields={},
            content_hash="hash-new",
            match_key="corp:decision:1",
            previous_id="corp-1",
            root_id="corp-1",
            valid_from=None,
            created_at=now,
            updated_at=now,
            created_by="tester",
        )
        versioned_record = _make_memory_record(versioned_out)

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )

        with (
            patch.object(
                memory_writes,
                "handle_memory_write",
                new=AsyncMock(
                    return_value=MemoryWriteResponse(
                        status="versioned", record=versioned_record
                    )
                ),
            ),
            patch.object(
                memory_writes, "get_memory", new=AsyncMock(return_value=versioned_out)
            ),
        ):
            result = await crud.update_memory(
                session,
                "corp-1",
                MemoryUpdate(content="updated content"),
                actor="agent",
            )

        self.assertEqual(result.id, "corp-2")
        self.assertEqual(result.version, 2)
        self.assertEqual(result.previous_id, "corp-1")
        self.assertEqual(result.root_id, "corp-1")

    async def test_corporate_update_uses_append_version_write_mode(self):
        from src import crud, memory_writes

        existing = _make_memory(
            domain=DomainEnum.corporate,
            entity_type="Decision",
            match_key="corp:decision:1",
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        captured_request = {}

        async def capture_write(session, request, *, actor="agent", _commit=True):
            captured_request["req"] = request
            out = _make_memory_out(existing)
            return MemoryWriteResponse(status="versioned", record=_make_memory_record(out))

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            await crud.update_memory(
                session, "mem-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertEqual(captured_request["req"].write_mode.value, "append_version")

    async def test_corporate_update_preserves_root_id_across_versions(self):
        from src import crud, memory_writes

        existing = _make_memory(
            mem_id="corp-1",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            match_key="corp:d:1",
            root_id="corp-1",
            version=2,  # already on version 2
        )
        now = datetime.now(timezone.utc)
        versioned_out = MemoryOut(
            id="corp-3",
            domain="corporate",
            entity_type="Decision",
            content="v3",
            owner="alice",
            status="active",
            version=3,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            obsidian_ref=None,
            custom_fields={},
            content_hash="hash-v3",
            match_key="corp:d:1",
            previous_id="corp-1",
            root_id="corp-1",  # root_id stays at the original record
            valid_from=None,
            created_at=now,
            updated_at=now,
            created_by="tester",
        )

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )

        with (
            patch.object(
                memory_writes,
                "handle_memory_write",
                new=AsyncMock(
                    return_value=MemoryWriteResponse(
                        status="versioned",
                        record=_make_memory_record(versioned_out),
                    )
                ),
            ),
            patch.object(
                memory_writes, "get_memory", new=AsyncMock(return_value=versioned_out)
            ),
        ):
            result = await crud.update_memory(
                session, "corp-1", MemoryUpdate(content="v3"), actor="agent"
            )

        self.assertEqual(result.root_id, "corp-1")


class TestUpdateRegressions(unittest.IsolatedAsyncioTestCase):
    """Regression tests for known historical failures."""

    async def test_update_returns_none_when_memory_not_found(self):
        """update_memory must return None for unknown IDs (no 500 crash)."""
        from src import crud

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: None
        )

        result = await crud.update_memory(
            session, "nonexistent-id", MemoryUpdate(content="x"), actor="agent"
        )

        self.assertIsNone(result)

    async def test_update_does_not_create_duplicate_for_build_without_match_key(self):
        """
        Regression: pre-fix, brain_update sent to POST /write without match_key,
        causing a new record to be created instead of updating the existing one.
        Post-fix: update_memory() must always pass the existing match_key.
        """
        from src import crud, memory_writes

        existing = _make_memory(mem_id="build-1", match_key="build:note:1")
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        write_calls = []

        async def capture_write(session, request, *, actor="agent", _commit=True):
            write_calls.append(request)
            out = _make_memory_out(existing)
            return MemoryWriteResponse(status="updated", record=_make_memory_record(out))

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            await crud.update_memory(
                session, "build-1", MemoryUpdate(content="new content"), actor="agent"
            )

        # Must have been called exactly once
        self.assertEqual(len(write_calls), 1)
        # Must have passed the existing match_key (not None)
        self.assertEqual(write_calls[0].record.match_key, "build:note:1")

    async def test_personal_update_uses_upsert_not_append_version(self):
        """personal domain is mutable — must never use append_version."""
        from src import crud, memory_writes

        existing = _make_memory(
            domain=DomainEnum.personal, entity_type="Note", match_key="personal:note:1"
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        captured_modes = []

        async def capture_write(session, request, *, actor="agent", _commit=True):
            captured_modes.append(request.write_mode.value)
            out = _make_memory_out(existing)
            return MemoryWriteResponse(status="updated", record=_make_memory_record(out))

        with (
            patch.object(memory_writes, "handle_memory_write", new=capture_write),
            patch.object(
                memory_writes,
                "get_memory",
                new=AsyncMock(return_value=_make_memory_out(existing)),
            ),
        ):
            await crud.update_memory(
                session, "mem-1", MemoryUpdate(content="new"), actor="agent"
            )

        self.assertNotIn("append_version", captured_modes)
        self.assertIn("upsert", captured_modes)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5.2: Run the tests — all should PASS**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_update_e2e.py -v
```

Expected: all PASS. If any fail, there is a real regression in the update logic — fix it before continuing.

- [ ] **Step 5.3: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/tests/test_update_e2e.py
git commit -m "test(update): add brain_update invariant E2E tests and regressions"
```

---

## Task 6: Extend `/readyz` with vector store check

**Files:**
- Modify: `unified/src/api/v1/health.py`

- [ ] **Step 6.1: Write the failing test first**

Add to a new file `unified/tests/test_health_endpoint.py`:

```python
# unified/tests/test_health_endpoint.py
"""Tests for extended /readyz health endpoint."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


class TestReadyzVectorStoreField:
    """Verify /readyz returns vector_store field."""

    @pytest.mark.asyncio
    async def test_readyz_returns_vector_store_field(self):
        from src.api.v1.health import readyz

        with (
            patch("src.api.v1.health.AsyncSessionLocal") as mock_session_class,
            patch("src.api.v1.health._check_vector_store", new=AsyncMock(return_value="ok")),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.execute = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await readyz()

        assert "vector_store" in result

    @pytest.mark.asyncio
    async def test_readyz_vector_store_ok_when_ollama_responds(self):
        from src.api.v1.health import readyz

        with (
            patch("src.api.v1.health.AsyncSessionLocal") as mock_session_class,
            patch("src.api.v1.health._check_vector_store", new=AsyncMock(return_value="ok")),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.execute = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await readyz()

        assert result["vector_store"] == "ok"

    @pytest.mark.asyncio
    async def test_readyz_vector_store_degraded_when_ollama_down(self):
        from src.api.v1.health import readyz

        with (
            patch("src.api.v1.health.AsyncSessionLocal") as mock_session_class,
            patch(
                "src.api.v1.health._check_vector_store",
                new=AsyncMock(return_value="degraded"),
            ),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.execute = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await readyz()

        assert result["vector_store"] == "degraded"
```

- [ ] **Step 6.2: Run to confirm tests FAIL**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_health_endpoint.py -v
```

Expected: FAIL — `_check_vector_store` not found in `src.api.v1.health`.

- [ ] **Step 6.3: Implement the changes in `health.py`**

Replace the entire content of `unified/src/api/v1/health.py` with:

```python
"""Health check endpoints."""

from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ...auth import require_auth
from ...config import get_config
from ...db import AsyncSessionLocal

router = APIRouter(tags=["health"])
log = structlog.get_logger()

_OLLAMA_CHECK_TIMEOUT = 3.0


async def _check_vector_store() -> str:
    """
    Check if Ollama embedding service is reachable.
    Returns 'ok' or 'degraded'.
    """
    config = get_config()
    ollama_url = config.embedding.url
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_CHECK_TIMEOUT) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            return "ok" if r.is_success else "degraded"
    except Exception:
        return "degraded"


@router.get("/healthz")
async def healthz() -> dict:
    """Basic health check - always returns OK."""
    return {"status": "ok", "service": "openbrain-unified"}


@router.get("/readyz")
async def readyz() -> dict:
    """
    Readiness check — verifies database connectivity and vector store availability.

    Returns:
        status: 'ok' | 'degraded'
        db: 'ok' | 'error'
        vector_store: 'ok' | 'degraded'
    """
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("readyz_db_check_failed", error=str(exc))
        db_status = "error"

    vector_store_status = await _check_vector_store()

    overall = "ok" if db_status == "ok" else "degraded"
    payload = {
        "status": overall,
        "service": "openbrain-unified",
        "db": db_status,
        "vector_store": vector_store_status,
    }

    if overall != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/health")
async def health(
    _user: dict = Depends(require_auth),
) -> dict:
    """Detailed health check (requires authentication)."""
    return await readyz()
```

- [ ] **Step 6.4: Run health tests — should now PASS**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_health_endpoint.py -v
```

Expected: all PASS.

- [ ] **Step 6.5: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/src/api/v1/health.py unified/tests/test_health_endpoint.py
git commit -m "feat(health): add vector_store status to /readyz endpoint"
```

---

## Task 7: Extend `brain_capabilities` in gateway

**Files:**
- Modify: `unified/mcp-gateway/src/main.py`

- [ ] **Step 7.1: Replace the `brain_capabilities` function**

In `unified/mcp-gateway/src/main.py`, find and replace the existing `brain_capabilities` function (lines 165–185) with:

```python
@mcp.tool()
async def brain_capabilities() -> dict:
    """
    Check the operational status of the OpenBrain Memory Platform.

    Queries the backend /readyz endpoint for real-time status of the
    database and vector store (Ollama). Also reports Obsidian local tools
    availability based on ENABLE_LOCAL_OBSIDIAN_TOOLS environment variable.
    """
    # Query backend health
    backend_status = "unavailable"
    db_status = "unknown"
    vector_store_status = "unknown"

    try:
        async with _client() as c:
            r = await c.get("/readyz", timeout=5.0)
            if r.is_success:
                health = r.json()
                backend_status = "ok"
                db_status = health.get("db", "unknown")
                vector_store_status = health.get("vector_store", "unknown")
            else:
                backend_status = "degraded"
    except Exception:
        backend_status = "unavailable"

    obsidian_enabled = _obsidian_local_tools_enabled()
    obsidian_tools = (
        ["obsidian_vaults", "obsidian_read_note", "obsidian_sync",
         "obsidian_write_note", "obsidian_export", "obsidian_collection",
         "obsidian_bidirectional_sync", "obsidian_sync_status", "obsidian_update_note"]
        if obsidian_enabled
        else []
    )

    tier_2_tools = ["list", "get_context", "delete", "export", "sync_check"]
    if obsidian_enabled:
        tier_2_tools.extend(["obsidian_vaults", "obsidian_read_note", "obsidian_sync"])

    return {
        "platform": "OpenBrain V1 (Gateway)",
        "backend": {
            "status": backend_status,
            "url": BRAIN_URL,
            "db": db_status,
            "vector_store": vector_store_status,
        },
        "obsidian_local": {
            "status": "enabled" if obsidian_enabled else "disabled",
            "reason": (
                None
                if obsidian_enabled
                else (
                    f"Set {OBSIDIAN_LOCAL_TOOLS_ENV}=1 to enable local Obsidian tools. "
                    "Requires trusted local stdio gateway."
                )
            ),
            "tools": obsidian_tools,
        },
        "tier_1_core": {
            "status": "stable",
            "tools": ["search", "get", "store", "update"],
        },
        "tier_2_advanced": {
            "status": "active",
            "tools": tier_2_tools,
        },
        "tier_3_admin": {
            "status": "guarded",
            "tools": ["store_bulk", "upsert_bulk", "maintain"],
        },
    }
```

- [ ] **Step 7.2: Verify gateway imports without error**

```bash
cd /Users/gniewkob/Repos/openbrain/unified/mcp-gateway
python -c "from src.main import mcp; print('gateway imports OK')"
```

Expected: `gateway imports OK`

- [ ] **Step 7.3: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/mcp-gateway/src/main.py
git commit -m "feat(gateway): brain_capabilities queries /readyz for real backend status"
```

---

## Task 8: Error Normalization — `retryable` field + `HTTPException` envelope

**Files:**
- Modify: `unified/src/schemas.py`
- Modify: `unified/src/exceptions.py`

- [ ] **Step 8.1: Write failing tests**

Create `unified/tests/test_error_normalization.py`:

```python
# unified/tests/test_error_normalization.py
"""Tests for normalized error envelopes with retryable field."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture()
def app_with_handlers():
    """FastAPI app with registered exception handlers."""
    from fastapi import FastAPI
    from src.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-404")
    async def trigger_404():
        raise HTTPException(status_code=404, detail="Memory not found")

    @app.get("/trigger-403")
    async def trigger_403():
        raise HTTPException(status_code=403, detail="Access denied")

    @app.get("/trigger-409")
    async def trigger_409():
        raise HTTPException(status_code=409, detail="Conflict")

    @app.get("/trigger-422")
    async def trigger_422():
        raise HTTPException(status_code=422, detail="Semantic error")

    @app.get("/trigger-503")
    async def trigger_503():
        raise HTTPException(status_code=503, detail="Service unavailable")

    @app.get("/trigger-500")
    async def trigger_500():
        raise RuntimeError("Unexpected internal error")

    return app


class TestErrorEnvelopeShape:
    """Every error response must use the ErrorDetail envelope."""

    def test_404_has_error_envelope(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-404")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "retryable" in body["error"]

    def test_403_has_error_envelope(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-403")
        assert r.status_code == 403
        body = r.json()
        assert "error" in body
        assert "retryable" in body["error"]

    def test_500_has_error_envelope(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-500")
        assert r.status_code == 500
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == "internal_error"
        assert "retryable" in body["error"]


class TestRetryableField:
    """retryable must be True only for 503."""

    def test_404_not_retryable(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-404")
        assert r.json()["error"]["retryable"] is False

    def test_503_is_retryable(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-503")
        assert r.json()["error"]["retryable"] is True

    def test_500_not_retryable(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-500")
        assert r.json()["error"]["retryable"] is False


class TestErrorCodes:
    """HTTP status codes map to semantic error codes."""

    def test_404_maps_to_not_found_code(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-404")
        assert r.json()["error"]["code"] == "not_found"

    def test_403_maps_to_access_denied_code(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-403")
        assert r.json()["error"]["code"] == "access_denied"

    def test_409_maps_to_conflict_code(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-409")
        assert r.json()["error"]["code"] == "conflict"

    def test_503_maps_to_service_unavailable_code(self, app_with_handlers):
        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        r = client.get("/trigger-503")
        assert r.json()["error"]["code"] == "service_unavailable"


class TestErrorDetailSchema:
    """ErrorDetail Pydantic model must include retryable field."""

    def test_error_detail_has_retryable_field(self):
        from src.schemas import ErrorDetail

        err = ErrorDetail(code="test_error", message="Test message", retryable=True)
        assert err.retryable is True

    def test_error_detail_retryable_defaults_to_false(self):
        from src.schemas import ErrorDetail

        err = ErrorDetail(code="test_error", message="Test message")
        assert err.retryable is False
```

- [ ] **Step 8.2: Run — confirm tests FAIL**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_error_normalization.py -v 2>&1 | head -40
```

Expected: FAIL — `ErrorDetail` has no `retryable` field; `HTTPException` not wrapped in error envelope.

- [ ] **Step 8.3: Add `retryable` to `ErrorDetail` in `schemas.py`**

In `unified/src/schemas.py`, find the `ErrorDetail` class (around line 596) and replace it:

```python
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    retryable: bool = False
```

- [ ] **Step 8.4: Add `HTTPException` handler and status code map to `exceptions.py`**

In `unified/src/exceptions.py`, find `register_exception_handlers` and replace the entire function plus add the new HTTP status code map above it:

```python
# Maps FastAPI/Starlette HTTP status codes to semantic error codes
_HTTP_STATUS_TO_CODE: dict[int, str] = {
    400: "validation_error",
    401: "auth_required",
    403: "access_denied",
    404: "not_found",
    409: "conflict",
    422: "semantic_error",
    429: "rate_limit_exceeded",
    500: "internal_error",
    503: "service_unavailable",
}

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset([503, 429])


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """
    Wrap FastAPI HTTPException in the standard ErrorDetail envelope.

    Maps status code to a semantic error code and sets retryable flag.
    """
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, "internal_error")
    retryable = exc.status_code in _RETRYABLE_STATUS_CODES

    # Use detail if it's a plain string message; else use the safe default
    if isinstance(exc.detail, str):
        message = exc.detail
    else:
        message = _HTTP_STATUS_TO_CODE.get(exc.status_code, "Request failed")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            }
        },
    )


def register_exception_handlers(app: Any) -> None:
    """Register all exception handlers with FastAPI app."""
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")

    # HTTPException handler (FastAPI raises these for 404, 403, etc.)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # OpenBrain domain exception handler
    app.add_exception_handler(OpenBrainError, openbrain_exception_handler)

    # Catch-all for unexpected exceptions
    app.add_exception_handler(Exception, generic_exception_handler)
```

Also update `generic_exception_handler` to include `retryable`:

```python
async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handler for unhandled exceptions."""
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, OpenBrainError):
        return await openbrain_exception_handler(request, exc)

    # Unexpected exception
    if is_production():
        content = {
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred",
                "retryable": False,
            }
        }
    else:
        content = {
            "error": {
                "code": "internal_error",
                "message": str(exc),
                "details": {"type": type(exc).__name__},
                "retryable": False,
            }
        }

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
    )
```

And update `openbrain_exception_handler` to include `retryable`:

```python
async def openbrain_exception_handler(
    request: Request,
    exc: OpenBrainError,
) -> JSONResponse:
    """Handler for OpenBrain exceptions."""
    retryable = exc.status_code in _RETRYABLE_STATUS_CODES
    response = create_error_response(exc, request)
    response["error"]["retryable"] = retryable
    return JSONResponse(
        status_code=exc.status_code,
        content=response,
    )
```

- [ ] **Step 8.5: Run error normalization tests — should now PASS**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_error_normalization.py -v
```

Expected: all PASS.

- [ ] **Step 8.6: Run full test suite to verify no regressions**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v --ignore=tests/test_api_endpoints_live.py --ignore=tests/validate_openbrain_api.py 2>&1 | tail -40
```

Expected: all tests PASS. Fix any failures before committing.

- [ ] **Step 8.7: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/src/schemas.py unified/src/exceptions.py unified/tests/test_error_normalization.py
git commit -m "feat(errors): normalize HTTPException to ErrorDetail envelope with retryable field"
```

---

## Final Verification

- [ ] **Run complete test suite one last time**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/ -v \
  --ignore=tests/test_api_endpoints_live.py \
  --ignore=tests/validate_openbrain_api.py \
  2>&1 | tail -20
```

Expected output ends with something like:
```
===== N passed, 0 failed in X.XXs =====
```

- [ ] **Verify gateway imports cleanly**

```bash
cd /Users/gniewkob/Repos/openbrain/unified/mcp-gateway
python -c "from src.main import mcp; print('OK')"
```

- [ ] **Tag completion**

```bash
cd /Users/gniewkob/Repos/openbrain
git tag track-a-p0-complete
```

---

## Definition of Done Checklist

- [ ] `SecretScanMiddleware` blocks writes with plaintext secrets (8 patterns)
- [ ] Scanner never logs matched secret values — only pattern name
- [ ] `DISABLE_SECRET_SCANNING=1` allows bypass in test environments
- [ ] Contract parity tests pass (gateway ↔ backend schema 1:1)
- [ ] `brain_update` invariant tests pass (build/personal/corporate + regressions)
- [ ] `/readyz` returns `vector_store` status
- [ ] `brain_capabilities` returns real `backend.db` + `backend.vector_store`
- [ ] `brain_capabilities` shows Obsidian `enabled/disabled` with reason
- [ ] All error responses use `ErrorDetail` envelope
- [ ] `retryable: true` only for 503 and 429
- [ ] No existing tests broken
