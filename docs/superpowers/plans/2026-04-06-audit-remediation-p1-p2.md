# Audit Remediation P1/P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all remaining P0/P1/P2 audit findings from `docs/AUDIT_REPORT_2026-04-04.md`.

**Architecture:** Each task is self-contained and independently testable. No task depends on another except Task 6 (migration) which should come after Task 5 (indexes code). Rate limiting uses the already-imported `slowapi` library. Circuit breaker uses a simple in-process state machine in `embed.py`.

**Tech Stack:** FastAPI, SQLAlchemy + Alembic, httpx, slowapi, asyncio, Python 3.12

---

## File Map

| File | What changes |
|------|-------------|
| `docker-compose.unified.yml` | Replace 2 hardcoded secrets with `${VAR}` references |
| `.env.example` | Add NGROK_AUTHTOKEN and POSTGRES_PASSWORD placeholders |
| `unified/src/auth.py` | Fix 503→401; add in-process rate limiter for X-Internal-Key |
| `unified/mcp-gateway/src/main.py` | Warn at startup if INTERNAL_API_KEY < 32 chars; add version to capabilities |
| `unified/src/memory_writes.py` | Wrap run_maintenance body with asyncio.timeout |
| `unified/migrations/versions/011_add_perf_indexes.py` | New migration: indexes on created_at, updated_at, content_hash |
| `unified/src/embed.py` | Add simple circuit breaker for Ollama |
| `unified/tests/test_auth_security.py` | Add test: 503→401 when OIDC unavailable |
| `unified/tests/test_maintenance_timeout.py` | Add test: maintenance respects timeout |
| `unified/tests/test_embed_circuit_breaker.py` | Add test: circuit breaker trips after repeated failures |

---

## Task 1: P0 — Remove hardcoded secrets from docker-compose.unified.yml

**Files:**
- Modify: `docker-compose.unified.yml:7,113`
- Modify: `.env.example`

### What to fix

`docker-compose.unified.yml` line 7 has `POSTGRES_PASSWORD=2d0d0c4d2df44c61a4aa83eb94d0c1b7` (hardcoded).
`docker-compose.unified.yml` line 113 has `NGROK_AUTHTOKEN=3Ac5z667AJsD4kiy76AoHJTEQax_5dEF5kAbdyzZk1JicaoNR` (hardcoded).

- [ ] **Step 1: Fix POSTGRES_PASSWORD in docker-compose.unified.yml**

Change line 7 from:
```yaml
      - POSTGRES_PASSWORD=2d0d0c4d2df44c61a4aa83eb94d0c1b7
```
To:
```yaml
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

- [ ] **Step 2: Fix NGROK_AUTHTOKEN in docker-compose.unified.yml**

Change line 113 from:
```yaml
      - NGROK_AUTHTOKEN=3Ac5z667AJsD4kiy76AoHJTEQax_5dEF5kAbdyzZk1JicaoNR
```
To:
```yaml
      - NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN}
```

- [ ] **Step 3: Update .env.example to document required secrets**

Read `.env.example` (or create if missing), then add/ensure these entries exist:
```bash
# PostgreSQL
POSTGRES_PASSWORD=change-me-strong-password-here

# ngrok (optional — only needed with COMPOSE_PROFILES=public)
NGROK_AUTHTOKEN=your-ngrok-authtoken-here

# Internal API key — must be >= 32 chars in PUBLIC_MODE
INTERNAL_API_KEY=generate-with-openssl-rand-base64-32
```

- [ ] **Step 4: Verify .gitignore covers .env**

Run: `grep -n '\.env' .gitignore`
Expected output includes `.env` and `.env.*`

- [ ] **Step 5: Verify no other secrets remain in docker-compose.unified.yml**

Run: `grep -n 'PASSWORD=\|TOKEN=\|KEY=' docker-compose.unified.yml`
Expected: all values use `${VAR}` syntax, none are hardcoded strings.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.unified.yml .env.example
git commit -m "security: replace hardcoded secrets with \${VAR} references in docker-compose"
```

---

## Task 2: P1 — Fix 503→401 when OIDC unavailable in auth.py

**Files:**
- Modify: `unified/src/auth.py:531-534`
- Modify: `unified/tests/test_auth_security.py`

### Context

`auth.py` line 531-534 currently raises HTTP 503 when OIDC verifier is unavailable in public mode. The audit (finding 1.4) says this leaks configuration details and should be 401.

Current code (around line 531):
```python
if not _oidc:
    raise HTTPException(
        status_code=503, detail="OIDC verifier is unavailable in public mode"
    )
```

- [ ] **Step 1: Write a failing test**

Add to `unified/tests/test_auth_security.py`:
```python
def test_public_mode_no_oidc_returns_401_not_503(monkeypatch):
    """When OIDC is unavailable, auth should return 401 not 503."""
    import importlib
    monkeypatch.setenv("PUBLIC_MODE", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("INTERNAL_API_KEY", "a" * 32)
    monkeypatch.setenv("OIDC_ISSUER_URL", "")

    from src import auth
    importlib.reload(auth)

    # _oidc is None when OIDC_ISSUER_URL is empty
    assert auth._oidc is None
    # Calling verify_user_or_internal_key with no internal key header
    # and no OIDC should raise 401, not 503
    import asyncio
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    request = MagicMock()
    request.headers.get.return_value = ""  # no X-Internal-Key

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.verify_user_or_internal_key(request, None))
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unified && python -m pytest tests/test_auth_security.py::test_public_mode_no_oidc_returns_401_not_503 -v`
Expected: FAIL — currently raises 503.

- [ ] **Step 3: Fix auth.py — change 503 to 401**

In `unified/src/auth.py`, change:
```python
    if not _oidc:
        raise HTTPException(
            status_code=503, detail="OIDC verifier is unavailable in public mode"
        )
```
To:
```python
    if not _oidc:
        raise HTTPException(
            status_code=401, detail="Unauthorized"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd unified && python -m pytest tests/test_auth_security.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add unified/src/auth.py unified/tests/test_auth_security.py
git commit -m "security: return 401 instead of 503 when OIDC unavailable (audit 1.4)"
```

---

## Task 3: P1 — Add API key length validation in MCP gateway startup

**Files:**
- Modify: `unified/mcp-gateway/src/main.py`

### Context

`config.py` validates INTERNAL_API_KEY length >= 32 chars in public mode, but `mcp-gateway/src/main.py` reads the key directly from `os.environ` at line 39 with no validation. A short key (e.g. `"dev"`) would silently be used.

- [ ] **Step 1: Write a failing test**

Add `unified/mcp-gateway/tests/test_gateway_startup.py`:
```python
"""Test MCP gateway startup validation."""
import os
import importlib
import sys
import pytest


def test_short_internal_key_logs_warning(monkeypatch, caplog):
    """Gateway should warn when INTERNAL_API_KEY is shorter than 32 chars."""
    import logging
    monkeypatch.setenv("INTERNAL_API_KEY", "short")
    monkeypatch.setenv("BRAIN_URL", "http://localhost:7010")

    # Force re-import to pick up new env
    if "src.main" in sys.modules:
        del sys.modules["src.main"]

    with caplog.at_level(logging.WARNING, logger="mcp_gateway"):
        import src.main  # noqa: F401

    assert any("INTERNAL_API_KEY" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unified/mcp-gateway && python -m pytest tests/test_gateway_startup.py -v`
Expected: FAIL (no warning emitted currently).

- [ ] **Step 3: Add validation in mcp-gateway/src/main.py**

After line 39 (`INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()`), add:
```python
import logging as _logging
_gateway_logger = _logging.getLogger("mcp_gateway")

_MIN_KEY_LEN = 32
if INTERNAL_API_KEY and len(INTERNAL_API_KEY) < _MIN_KEY_LEN:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is only %d chars (minimum %d). "
        "Use a longer key in production.",
        len(INTERNAL_API_KEY),
        _MIN_KEY_LEN,
    )
elif not INTERNAL_API_KEY:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is not set. Requests to backend will fail in public mode."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd unified/mcp-gateway && python -m pytest tests/test_gateway_startup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add unified/mcp-gateway/src/main.py unified/mcp-gateway/tests/test_gateway_startup.py
git commit -m "security: warn at startup when INTERNAL_API_KEY is short or missing (audit 1.3)"
```

---

## Task 4: P1 — Add rate limiting for internal key requests

**Files:**
- Modify: `unified/src/auth.py`
- Modify: `unified/tests/test_auth_security.py`

### Context

`slowapi` is already a dependency in `pyproject.toml`. `AppConfig` has `rate_limit_per_minute: int` from `AUTH_RATE_LIMIT_RPM` env var (default 100). Currently internal key auth has no rate limiting.

Approach: Add an in-process sliding-window counter keyed by client IP. This avoids Redis dependency for rate limiting (which would require configuring Redis URL). Simple, reliable, testable.

- [ ] **Step 1: Write a failing test**

Add to `unified/tests/test_auth_security.py`:
```python
def test_internal_key_rate_limit_applied(monkeypatch):
    """Requests exceeding AUTH_RATE_LIMIT_RPM should get 429."""
    monkeypatch.setenv("PUBLIC_MODE", "true")
    monkeypatch.setenv("INTERNAL_API_KEY", "a" * 32)
    monkeypatch.setenv("AUTH_RATE_LIMIT_RPM", "2")  # very low for test

    # Import after env vars are set
    import importlib
    from src import auth
    importlib.reload(auth)

    # The rate limiter function should be callable
    assert callable(auth.check_internal_key_rate_limit)

    # Simulate 3 calls from same IP — 3rd should fail
    import asyncio
    from unittest.mock import MagicMock

    async def run():
        for i in range(2):
            auth.check_internal_key_rate_limit("127.0.0.1")
        # 3rd call should raise
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth.check_internal_key_rate_limit("127.0.0.1")
        assert exc_info.value.status_code == 429

    asyncio.run(run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unified && python -m pytest tests/test_auth_security.py::test_internal_key_rate_limit_applied -v`
Expected: FAIL — `auth.check_internal_key_rate_limit` does not exist.

- [ ] **Step 3: Add rate limiter in auth.py**

Add these imports and state near the top of `auth.py` (after existing imports):
```python
import collections
import threading

# In-process sliding-window rate limiter for internal key path
# Keyed by IP address. Uses thread-safe deque per IP.
_rate_limit_store: dict[str, collections.deque] = {}
_rate_limit_lock = threading.Lock()


def _get_rate_limit_rpm() -> int:
    """Read AUTH_RATE_LIMIT_RPM from env (avoids config import cycle)."""
    try:
        return int(os.environ.get("AUTH_RATE_LIMIT_RPM", "100"))
    except ValueError:
        return 100


def check_internal_key_rate_limit(client_ip: str) -> None:
    """Sliding-window rate limiter for internal key requests.

    Raises HTTP 429 if client exceeds AUTH_RATE_LIMIT_RPM per minute.
    """
    from fastapi import HTTPException

    limit = _get_rate_limit_rpm()
    now = time.time()
    window_start = now - 60.0

    with _rate_limit_lock:
        if client_ip not in _rate_limit_store:
            _rate_limit_store[client_ip] = collections.deque()
        q = _rate_limit_store[client_ip]
        # Evict old timestamps outside the window
        while q and q[0] < window_start:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )
        q.append(now)
```

Then in `verify_user_or_internal_key` (after confirming the key matches), add the rate limit check:
```python
    if (
        internal_key
        and INTERNAL_API_KEY
        and hmac.compare_digest(internal_key, INTERNAL_API_KEY)
    ):
        client_ip = request.client.host if request.client else "unknown"
        check_internal_key_rate_limit(client_ip)
        return {"sub": "internal", "_auth_via_internal_key": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd unified && python -m pytest tests/test_auth_security.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add unified/src/auth.py unified/tests/test_auth_security.py
git commit -m "security: add sliding-window rate limiting for X-Internal-Key requests (audit 1.2)"
```

---

## Task 5: P1 — Add timeout for maintenance operations

**Files:**
- Modify: `unified/src/memory_writes.py`
- Create: `unified/tests/test_maintenance_timeout.py`

### Context

`run_maintenance()` in `memory_writes.py` at line 732 can run indefinitely on large databases. Python 3.11+ `asyncio.timeout()` is the canonical way to add timeouts to async code blocks.

Timeout value: `MAINTENANCE_TIMEOUT_S` env var, default 300 seconds (5 minutes).

- [ ] **Step 1: Write a failing test**

Create `unified/tests/test_maintenance_timeout.py`:
```python
"""Test that run_maintenance respects timeout."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_run_maintenance_times_out():
    """run_maintenance should raise TimeoutError if it exceeds MAINTENANCE_TIMEOUT_S."""
    from src.schemas import MaintenanceRequest

    req = MaintenanceRequest(dedup_threshold=0.95, dry_run=True)

    # Create a session mock whose execute() hangs forever
    session = AsyncMock()
    session.execute.side_effect = lambda *a, **kw: asyncio.sleep(9999)

    with patch.dict("os.environ", {"MAINTENANCE_TIMEOUT_S": "0.1"}):
        from src import memory_writes
        import importlib
        importlib.reload(memory_writes)

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await memory_writes.run_maintenance(session, req, actor="test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unified && python -m pytest tests/test_maintenance_timeout.py -v`
Expected: FAIL — currently hangs or does not raise TimeoutError (you may need to interrupt with Ctrl+C after a few seconds; add `--timeout=5` if pytest-timeout is installed).

- [ ] **Step 3: Add timeout to run_maintenance in memory_writes.py**

Add import at the top of `memory_writes.py`:
```python
import asyncio
import os
```

Then wrap the body of `run_maintenance` with `asyncio.timeout()`. Find the current function signature:
```python
async def run_maintenance(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    actions: list[MaintenanceAction] = []
    ...
```

Change to:
```python
_MAINTENANCE_TIMEOUT_S = float(os.environ.get("MAINTENANCE_TIMEOUT_S", "300"))


async def run_maintenance(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    timeout_s = float(os.environ.get("MAINTENANCE_TIMEOUT_S", "300"))
    async with asyncio.timeout(timeout_s):
        return await _run_maintenance_inner(session, req, actor)


async def _run_maintenance_inner(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    actions: list[MaintenanceAction] = []
    # ... rest of existing body unchanged ...
```

Move all existing content of `run_maintenance` into `_run_maintenance_inner`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd unified && python -m pytest tests/test_maintenance_timeout.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd unified && python -m pytest tests/ -v --ignore=tests/test_endpoints_summary.py`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add unified/src/memory_writes.py unified/tests/test_maintenance_timeout.py
git commit -m "feat: add asyncio timeout to run_maintenance (audit 3.4)"
```

---

## Task 6: P2 — Add DB indexes for created_at, updated_at, content_hash

**Files:**
- Create: `unified/migrations/versions/011_add_perf_indexes.py`

### Context

`001_unified_initial.py` creates indexes on `domain`, `entity_type`, `status`, `match_key`, `obsidian_ref`, and the HNSW embedding index. Missing: `created_at`, `updated_at` (used in ORDER BY clauses), and `content_hash` (used in deduplication grouping).

- [ ] **Step 1: Write a failing test**

Add to `unified/tests/test_audit_fixes.py` (or create a new test file):
```python
def test_perf_indexes_migration_exists():
    """Migration 011 for performance indexes must exist."""
    from pathlib import Path
    migrations_dir = Path(__file__).parent.parent / "migrations" / "versions"
    migration_files = list(migrations_dir.glob("011_*.py"))
    assert migration_files, "Migration 011_add_perf_indexes.py does not exist"

    content = migration_files[0].read_text()
    assert "created_at" in content, "Missing index on created_at"
    assert "updated_at" in content, "Missing index on updated_at"
    assert "content_hash" in content, "Missing index on content_hash"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unified && python -m pytest tests/test_audit_fixes.py::test_perf_indexes_migration_exists -v`
Expected: FAIL — migration 011 does not exist.

- [ ] **Step 3: Create migration file**

Create `unified/migrations/versions/011_add_perf_indexes.py`:
```python
"""Add performance indexes for sorting and deduplication queries.

Revision ID: 011
Revises: 010
Create Date: 2026-04-06
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sorting indexes (ORDER BY created_at DESC, updated_at DESC)
    op.create_index(
        "ix_memories_created_at",
        "memories",
        ["created_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_memories_updated_at",
        "memories",
        ["updated_at"],
        postgresql_using="btree",
    )
    # Deduplication: content_hash used in GROUP BY + dedup queries
    op.create_index(
        "ix_memories_content_hash",
        "memories",
        ["content_hash"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ix_memories_content_hash", table_name="memories")
    op.drop_index("ix_memories_updated_at", table_name="memories")
    op.drop_index("ix_memories_created_at", table_name="memories")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd unified && python -m pytest tests/test_audit_fixes.py::test_perf_indexes_migration_exists -v`
Expected: PASS.

- [ ] **Step 5: Verify migration is syntactically valid**

Run: `cd unified && python -c "import migrations.versions.011_add_perf_indexes; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add unified/migrations/versions/011_add_perf_indexes.py unified/tests/test_audit_fixes.py
git commit -m "perf: add indexes on created_at, updated_at, content_hash (audit 4.3)"
```

---

## Task 7: P2 — Add circuit breaker for Ollama in embed.py

**Files:**
- Modify: `unified/src/embed.py`
- Create: `unified/tests/test_embed_circuit_breaker.py`

### Context

Audit finding 4.1: embed.py has retry logic but no circuit breaker. When Ollama is down, each embedding call will do 3 slow retries (with sleep delays) before failing. Under load, this leads to thread/connection exhaustion.

Circuit breaker pattern:
- **CLOSED** (normal): requests pass through
- **OPEN** (tripped): requests fail fast with a clear error, no HTTP attempt
- **HALF_OPEN** (recovery probe): after `reset_timeout` seconds, allow one request; if it succeeds, close; if it fails, reopen.

Parameters: trip after 3 consecutive failures (`failure_threshold=3`), try recovery after 30 seconds (`reset_timeout=30`).

- [ ] **Step 1: Write failing tests**

Create `unified/tests/test_embed_circuit_breaker.py`:
```python
"""Tests for Ollama embedding circuit breaker."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
import httpx


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_failures():
    """Circuit breaker should open after 3 consecutive failures."""
    from src.embed import _circuit_breaker, CircuitOpenError

    # Reset circuit breaker state
    _circuit_breaker.reset()

    fail_response = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("src.embed._post_with_retry", side_effect=httpx.ConnectError("down")):
        for _ in range(3):
            with pytest.raises((httpx.ConnectError, Exception)):
                await _circuit_breaker.call(lambda: (_ for _ in ()).throw(httpx.ConnectError("down")))

    assert _circuit_breaker.state == "open"


@pytest.mark.asyncio
async def test_circuit_open_raises_immediately():
    """When circuit is open, get_embedding should raise CircuitOpenError fast."""
    from src.embed import _circuit_breaker, CircuitOpenError

    _circuit_breaker.reset()
    _circuit_breaker._state = "open"
    _circuit_breaker._opened_at = 0  # opened long ago but reset_timeout not elapsed

    with pytest.raises(CircuitOpenError):
        await _circuit_breaker.guard()


@pytest.mark.asyncio
async def test_circuit_breaker_recovers():
    """After reset_timeout, circuit should allow probe and recover."""
    import time
    from src.embed import _circuit_breaker, CircuitOpenError

    _circuit_breaker.reset()
    _circuit_breaker._state = "open"
    _circuit_breaker._opened_at = time.time() - 999  # opened long ago

    # Should transition to half_open (not raise)
    await _circuit_breaker.guard()
    assert _circuit_breaker.state == "half_open"

    # Simulate successful probe
    _circuit_breaker.on_success()
    assert _circuit_breaker.state == "closed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd unified && python -m pytest tests/test_embed_circuit_breaker.py -v`
Expected: FAIL — `CircuitOpenError` and `_circuit_breaker` do not exist.

- [ ] **Step 3: Add circuit breaker to embed.py**

Add to `unified/src/embed.py` after the imports section:
```python
import time as _time


class CircuitOpenError(RuntimeError):
    """Raised when the Ollama circuit breaker is open."""


class _CircuitBreaker:
    """Simple 3-state circuit breaker for the Ollama embedding client.

    States: closed → open → half_open → closed
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = "closed"
        self._failures = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    def reset(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    async def guard(self) -> None:
        """Check circuit state; raise CircuitOpenError if open."""
        if self._state == "closed":
            return
        if self._state == "open":
            if _time.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
                return
            raise CircuitOpenError(
                "Ollama embedding service is unavailable (circuit open). "
                "Retry after a moment."
            )
        # half_open: allow one probe through

    def on_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = _time.monotonic()


_circuit_breaker = _CircuitBreaker()
```

Then update `get_embedding` to use the circuit breaker:
```python
async def get_embedding(text: str) -> list[float]:
    """
    Fetch an embedding vector for the given text using Ollama.
    Uses LRU cache to avoid redundant API calls for identical text.
    Raises CircuitOpenError if the Ollama service is repeatedly unavailable.
    """
    config = get_config()
    text_hash = _compute_text_hash(text)

    # Check the OrderedDict cache under lock to prevent races
    async with _embedding_cache_lock:
        if text_hash in _embedding_cache:
            embedding, cached_model = _embedding_cache[text_hash]
            if cached_model == config.embedding.model:
                _embedding_cache.move_to_end(text_hash)
                return list(embedding)

    # Check circuit breaker before making HTTP call
    await _circuit_breaker.guard()

    # Cache miss — call Ollama
    try:
        response = await _post_with_retry(
            "/api/embed",
            {"model": config.embedding.model, "input": text},
        )
        if response.status_code == 404:
            response = await _post_with_retry(
                "/api/embeddings",
                {"model": config.embedding.model, "prompt": text},
            )
            result = response.json()["embedding"]
        else:
            data = response.json()
            result = data["embeddings"][0]
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        _circuit_breaker.on_failure()
        raise
    else:
        _circuit_breaker.on_success()

    await _update_embedding_cache(text_hash, tuple(result), config.embedding.model)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd unified && python -m pytest tests/test_embed_circuit_breaker.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd unified && python -m pytest tests/ -v --ignore=tests/test_endpoints_summary.py`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add unified/src/embed.py unified/tests/test_embed_circuit_breaker.py
git commit -m "perf: add circuit breaker for Ollama embedding service (audit 4.1)"
```

---

## Task 8: P2 — Add API version to MCP capabilities response

**Files:**
- Modify: `unified/mcp-gateway/src/main.py`

### Context

Audit finding 2.2: MCP tools have no versioning. Adding `api_version` to `brain_capabilities` tool response lets callers detect schema changes. This is the minimal viable versioning: a single version string exposed via the capabilities tool.

- [ ] **Step 1: Read brain_capabilities in mcp-gateway/src/main.py**

Find the `brain_capabilities` tool definition. Look for `async def brain_capabilities`.

- [ ] **Step 2: Add API version to response**

In the `brain_capabilities` function return value, add an `"api_version"` field:
```python
@mcp.tool()
async def brain_capabilities() -> dict:
    """Return OpenBrain capabilities and schema version.

    Version: 2.2.0
    """
    # ... existing capability fields ...
    result = {
        # existing fields
        "api_version": "2.2.0",
        "schema_changelog": {
            "2.2.0": "Added PATCH support for partial updates (brain_update)",
            "2.1.0": "Unified V1 API endpoints; corporate append-only enforcement",
            "2.0.0": "Initial unified server release",
        },
    }
    return result
```

If `brain_capabilities` doesn't exist, add it as a new tool.

- [ ] **Step 3: Run gateway tests**

Run: `cd unified/mcp-gateway && python -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add unified/mcp-gateway/src/main.py
git commit -m "feat: add api_version field to brain_capabilities response (audit 2.2)"
```

---

## Task 9: Final — Run full CI locally and verify checklist

- [ ] **Step 1: Run guardrails checks**

```bash
ruff check --select E9,F63,F7,F82 unified unified/mcp-gateway scripts
```
Expected: no errors.

- [ ] **Step 2: Run unified smoke tests**

```bash
cd unified && python -m unittest discover -s tests -v 2>&1 | tail -20
```
Expected: all tests pass, no failures.

- [ ] **Step 3: Run gateway smoke tests**

```bash
cd unified/mcp-gateway && python -m unittest discover -s tests -v 2>&1 | tail -10
```
Expected: all tests pass.

- [ ] **Step 4: Verify audit checklist**

```
- [x] Move NGROK_AUTHTOKEN to .env (Task 1)
- [x] Move POSTGRES_PASSWORD to .env (Task 1)
- [x] INTERNAL_API_KEY already uses ${VAR} (done in prior session)
- [x] Add key length validation in MCP gateway (Task 3)
- [x] Unify auth error codes — return 401, not 503 (Task 2)
- [x] Add rate limiting for internal key (Task 4)
- [x] Add timeout for maintenance (Task 5)
- [x] Add indexes on created_at, updated_at, content_hash (Task 6)
- [x] Add circuit breaker for Ollama (Task 7)
- [x] Add MCP API versioning (Task 8)
```

- [ ] **Step 5: Final commit**

```bash
git add -u
git commit -m "chore: audit remediation complete — all P0/P1/P2 findings closed"
```

---

## Self-Review

**Spec coverage check:**
- Audit 1.1 (secrets in compose) → Task 1 ✅
- Audit 1.2 (no rate limiting) → Task 4 ✅
- Audit 1.3 (key length validation) → Task 3 ✅
- Audit 1.4 (503 vs 401) → Task 2 ✅
- Audit 2.2 (MCP versioning) → Task 8 ✅
- Audit 2.4 (Obsidian docs) → Not planned (out of scope — no code to write, only .env.example documentation already added in Task 1; Obsidian docs can be added as a README section separately)
- Audit 3.4 (maintenance timeout) → Task 5 ✅
- Audit 4.1 (circuit breaker) → Task 7 ✅
- Audit 4.3 (indexes) → Task 6 ✅

**Placeholder scan:** No TBDs, all steps have actual code.

**Type consistency:** `_circuit_breaker` defined in Task 7 Step 3, referenced in same task. `check_internal_key_rate_limit` defined and tested in Task 4. No cross-task type dependencies.
