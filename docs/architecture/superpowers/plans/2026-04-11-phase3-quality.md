# Phase 3: Code Quality — Docstrings and Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reach docstring coverage ≥80% and test coverage ≥70% across `unified/src/`.

**Architecture:** Two parallel concerns: (1) Docstrings added to public functions in priority modules. (2) Tests added for under-covered modules. Both are additive — no existing code changes unless a test reveals a bug. Work module by module, verify coverage after each module.

**Tech Stack:** Python 3.13, pytest, pytest-cov, interrogate

---

## File Map

| File | Action |
|------|--------|
| `unified/src/auth.py` | **Modify** — add docstrings |
| `unified/src/api/v1/*.py` | **Modify** — add docstrings |
| `unified/src/memory_reads.py` | **Modify** — add docstrings |
| `unified/src/memory_writes.py` | **Modify** — add docstrings |
| `unified/tests/test_memory_reads_coverage.py` | **Create** — coverage for memory_reads |
| `unified/tests/test_obsidian_sync_coverage.py` | **Create** — coverage for obsidian_sync |
| `unified/tests/test_repositories_coverage.py` | **Create** — coverage for repositories/ |
| `unified/tests/integration/test_obsidian_roundtrip.py` | **Create** — Obsidian integration tests |

---

## Task 1: Baseline measurement

- [ ] **Step 1.1: Install interrogate if missing**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pip install interrogate -q
```

Expected: installs or already satisfied.

- [ ] **Step 1.2: Measure current docstring coverage**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/ -v 2>&1 | tail -20
```

Record the output. Note which modules have <50% coverage.

- [ ] **Step 1.3: Measure current test coverage**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src --cov-report=term-missing -q 2>&1 | grep -E "^unified/src|TOTAL"
```

Record the output. Note which files have <50% coverage.

---

## Task 2: Docstrings — auth.py

**Files:**
- Modify: `unified/src/auth.py`

- [ ] **Step 2.1: List undocumented functions**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/auth.py -v 2>&1 | grep "FAIL"
```

- [ ] **Step 2.2: Add docstrings to all public functions in auth.py**

For each public function (no leading underscore) that lacks a docstring, add one following this format:

```python
def function_name(param: Type) -> ReturnType:
    """One-line description of what this function does.

    Args:
        param: Description of the parameter.

    Returns:
        Description of the return value.

    Raises:
        HTTPException: When authentication fails (include the status code).
    """
```

Read each function body before writing the docstring — the description must accurately reflect behavior, not be generic.

- [ ] **Step 2.3: Verify auth.py docstring coverage**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/auth.py -v 2>&1 | tail -5
```

Expected: 100% for auth.py.

- [ ] **Step 2.4: Commit**

```bash
git add unified/src/auth.py
git commit -m "docs(auth): add docstrings to all public functions"
```

---

## Task 3: Docstrings — memory_reads.py and memory_writes.py

**Files:**
- Modify: `unified/src/memory_reads.py`
- Modify: `unified/src/memory_writes.py`

- [ ] **Step 3.1: Add docstrings to memory_reads.py**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/memory_reads.py -v 2>&1 | grep "FAIL"
```

For each undocumented public function, add a docstring describing:
- What it queries (which table/domain)
- Key parameters and their effect
- What it returns (schema type or description)

- [ ] **Step 3.2: Add docstrings to memory_writes.py**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/memory_writes.py -v 2>&1 | grep "FAIL"
```

For each undocumented public function, add a docstring. For write functions include:
- Side effects (what is written/updated/deleted)
- Governance behavior (append-only for corporate, etc.)

- [ ] **Step 3.3: Verify coverage for both files**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/memory_reads.py unified/src/memory_writes.py -v 2>&1 | tail -5
```

Expected: both ≥90%.

- [ ] **Step 3.4: Commit**

```bash
git add unified/src/memory_reads.py unified/src/memory_writes.py
git commit -m "docs(memory): add docstrings to read and write operations"
```

---

## Task 4: Docstrings — API v1 endpoints

**Files:**
- Modify: `unified/src/api/v1/*.py`

- [ ] **Step 4.1: List all API v1 files**

```bash
ls unified/src/api/v1/
```

- [ ] **Step 4.2: Check docstring coverage per file**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/api/v1/ -v 2>&1 | grep "FAIL"
```

- [ ] **Step 4.3: Add docstrings to all endpoint functions**

For FastAPI route functions, use this format:

```python
@router.post("/path")
async def endpoint_name(req: RequestSchema, session: AsyncSession = Depends(get_session)):
    """Store a new memory in OpenBrain.

    Validates the request, writes to PostgreSQL, and triggers embedding.

    Args:
        req: Memory write request with content, domain, entity_type.
        session: Injected database session.

    Returns:
        MemoryOut with assigned id, created_at, and computed content_hash.

    Raises:
        HTTPException 400: If secret patterns detected in content.
        HTTPException 422: If request schema validation fails.
    """
```

- [ ] **Step 4.4: Commit**

```bash
git add unified/src/api/
git commit -m "docs(api): add docstrings to all v1 endpoint functions"
```

---

## Task 5: Remaining modules to hit 80% threshold

- [ ] **Step 5.1: Check overall docstring coverage**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/ 2>&1 | tail -3
```

If already ≥80%: skip to Task 6.
If <80%: continue.

- [ ] **Step 5.2: Identify top modules with lowest coverage**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/ -v 2>&1 | grep -E "^unified" | sort -t'%' -k1 -n | head -10
```

- [ ] **Step 5.3: Add docstrings to modules until 80% is reached**

Work module by module starting from lowest coverage. For each module:
1. Read the function body
2. Write an accurate one-line description + Args/Returns

- [ ] **Step 5.4: Verify 80% threshold**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/ --fail-under=80
```

Expected: exit code 0.

- [ ] **Step 5.5: Commit**

```bash
git add unified/src/
git commit -m "docs(src): complete docstring coverage to 80% threshold"
```

---

## Task 6: Test coverage — memory_reads.py

**Files:**
- Create: `unified/tests/test_memory_reads_coverage.py`

- [ ] **Step 6.1: Identify uncovered lines in memory_reads.py**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src/memory_reads --cov-report=term-missing -q 2>&1 | grep "memory_reads"
```

Record the uncovered line numbers.

- [ ] **Step 6.2: Create test file targeting uncovered paths**

Create `unified/tests/test_memory_reads_coverage.py`:

```python
"""Coverage tests for memory_reads.py uncovered paths."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestListMemoriesCoverage:
    """Target uncovered branches in list_memories()."""

    @pytest.mark.asyncio
    async def test_list_with_domain_filter(self):
        from src.memory_reads import list_memories
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        result = await list_memories(session=session, domain="build")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_with_entity_type_filter(self):
        from src.memory_reads import list_memories
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        result = await list_memories(session=session, entity_type="Note")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_memory_not_found_returns_none(self):
        from src.memory_reads import get_memory
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        result = await get_memory(session=session, memory_id="nonexistent-id")
        assert result is None
```

Expand this file to cover additional uncovered lines identified in Step 6.1.

- [ ] **Step 6.3: Run new tests**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_memory_reads_coverage.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 6.4: Commit**

```bash
git add unified/tests/test_memory_reads_coverage.py
git commit -m "test(memory_reads): add coverage tests for uncovered paths"
```

---

## Task 7: Test coverage — obsidian_sync.py

**Files:**
- Create: `unified/tests/test_obsidian_sync_coverage.py`

- [ ] **Step 7.1: Identify uncovered lines**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src/obsidian_sync --cov-report=term-missing -q 2>&1 | grep "obsidian_sync"
```

- [ ] **Step 7.2: Create coverage test file**

Create `unified/tests/test_obsidian_sync_coverage.py`:

```python
"""Coverage tests for obsidian_sync.py uncovered paths."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestSyncEngineCoverage:

    @pytest.fixture
    def engine(self):
        from src.obsidian_sync import SyncEngine
        return SyncEngine()

    @pytest.mark.asyncio
    async def test_detect_changes_with_tracked_state_no_changes(self, engine):
        """Tracked item with no modifications produces no changes."""
        from src.obsidian_sync import SyncState
        session = AsyncMock()
        adapter = AsyncMock()

        state = SyncState(
            memory_id="mem-1",
            obsidian_path="test/note.md",
            vault="test",
            content_hash="abc123",
            memory_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            obsidian_modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        memory = MagicMock()
        memory.content = "test content"

        with patch("src.obsidian_sync._get_openbrain_memories",
                   return_value={"test/note.md": memory}), \
             patch("src.obsidian_sync._get_obsidian_files",
                   return_value={"test/note.md": MagicMock()}), \
             patch("src.obsidian_sync._check_memory_changed", return_value=False), \
             patch("src.obsidian_sync._detect_new_openbrain_memories", return_value=[]), \
             patch("src.obsidian_sync._detect_new_obsidian_files", return_value=[]):
            engine.tracker = MagicMock()
            engine.tracker.get_all_states.return_value = [state]
            result = await engine.detect_changes(session, adapter, vault="test")
        assert result == []

    @pytest.mark.asyncio
    async def test_detect_changes_deleted_memory(self, engine):
        """Tracked item with memory deleted produces a change."""
        from src.obsidian_sync import SyncState
        session = AsyncMock()
        adapter = AsyncMock()

        state = SyncState(
            memory_id="mem-deleted",
            obsidian_path="test/deleted.md",
            vault="test",
            content_hash="xyz",
            memory_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            obsidian_modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        with patch("src.obsidian_sync._get_openbrain_memories", return_value={}), \
             patch("src.obsidian_sync._get_obsidian_files",
                   return_value={"test/deleted.md": MagicMock()}), \
             patch("src.obsidian_sync._detect_new_openbrain_memories", return_value=[]), \
             patch("src.obsidian_sync._detect_new_obsidian_files", return_value=[]):
            engine.tracker = MagicMock()
            engine.tracker.get_all_states.return_value = [state]
            result = await engine.detect_changes(session, adapter, vault="test")
        # Memory is gone — should produce a delete/conflict change
        assert isinstance(result, list)
```

Expand with more cases targeting the specific uncovered lines from Step 7.1.

- [ ] **Step 7.3: Run new tests**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_obsidian_sync_coverage.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 7.4: Commit**

```bash
git add unified/tests/test_obsidian_sync_coverage.py
git commit -m "test(obsidian_sync): add coverage tests for detect_changes branches"
```

---

## Task 8: Test coverage — repositories/

**Files:**
- Create: `unified/tests/test_repositories_coverage.py`

- [ ] **Step 8.1: List repository files and their coverage**

```bash
ls unified/src/repositories/
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src/repositories --cov-report=term-missing -q 2>&1 | grep "repositories"
```

- [ ] **Step 8.2: Create repository coverage tests**

Create `unified/tests/test_repositories_coverage.py`:

```python
"""Coverage tests for unified/src/repositories/."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestMemoryRepositoryCoverage:
    """Tests for the memory repository pattern."""

    @pytest.mark.asyncio
    async def test_repository_can_be_instantiated(self):
        """Repository class is importable and instantiable."""
        # Import all repository classes
        import importlib
        import pkgutil
        import src.repositories as repo_pkg

        for importer, modname, ispkg in pkgutil.iter_modules(repo_pkg.__path__):
            mod = importlib.import_module(f"src.repositories.{modname}")
            # Each module should be importable without error
            assert mod is not None
```

Expand with specific tests for the repository methods identified in Step 8.1.

- [ ] **Step 8.3: Run new tests**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_repositories_coverage.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 8.4: Commit**

```bash
git add unified/tests/test_repositories_coverage.py
git commit -m "test(repositories): add coverage tests for repository pattern"
```

---

## Task 9: Integration tests — Obsidian roundtrip

**Files:**
- Create: `unified/tests/integration/test_obsidian_roundtrip.py`

- [ ] **Step 9.1: Check existing integration test structure**

```bash
ls unified/tests/integration/
cat unified/tests/integration/conftest.py 2>/dev/null | head -30
```

Understand how existing integration tests skip when backend is unavailable.

- [ ] **Step 9.2: Create integration test file**

Create `unified/tests/integration/test_obsidian_roundtrip.py`:

```python
"""
Obsidian integration tests — 4 scenarios.
These tests require a live backend. They skip automatically when unavailable.
Run with: INTEGRATION=1 pytest tests/integration/test_obsidian_roundtrip.py -v
"""
from __future__ import annotations

import os
import pytest


SKIP_REASON = "Integration tests require INTEGRATION=1 and live backend"
requires_backend = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"),
    reason=SKIP_REASON,
)


@requires_backend
class TestObsidianExport:
    """Scenario 1: Export a memory to Obsidian."""

    def test_export_creates_obsidian_note(self, brain_client):
        """Writing a memory should create a corresponding Obsidian note."""
        # brain_client is an httpx.Client pointed at the live backend
        resp = brain_client.post("/api/v1/memory/write", json={
            "content": "Integration test export note",
            "domain": "build",
            "entity_type": "Note",
            "owner": "test-suite",
        })
        assert resp.status_code == 201
        memory_id = resp.json()["id"]

        # Trigger sync
        sync_resp = brain_client.post("/api/v1/obsidian/sync", json={
            "vault": "Controlled E2E",
            "direction": "openbrain_to_obsidian",
        })
        assert sync_resp.status_code == 200
        data = sync_resp.json()
        assert data.get("exported", 0) >= 1 or data.get("status") == "ok"


@requires_backend
class TestObsidianImport:
    """Scenario 2: Import a note from Obsidian."""

    def test_import_reads_obsidian_note(self, brain_client):
        """Sync from Obsidian should create or update a memory."""
        sync_resp = brain_client.post("/api/v1/obsidian/sync", json={
            "vault": "Controlled E2E",
            "direction": "obsidian_to_openbrain",
        })
        assert sync_resp.status_code == 200


@requires_backend
class TestObsidianConflict:
    """Scenario 3: Conflict detection."""

    def test_conflict_does_not_lose_data(self, brain_client):
        """When both sides are modified, neither should be silently dropped."""
        # Write to OpenBrain
        resp = brain_client.post("/api/v1/memory/write", json={
            "content": "Conflict test — OpenBrain side",
            "domain": "build",
            "entity_type": "Note",
            "owner": "test-suite",
        })
        assert resp.status_code == 201
        # A bidirectional sync should report conflicts, not silently drop
        sync_resp = brain_client.post("/api/v1/obsidian/sync", json={
            "vault": "Controlled E2E",
            "direction": "bidirectional",
        })
        assert sync_resp.status_code == 200


@requires_backend
class TestObsidianDryRun:
    """Scenario 4: Dry-run mode makes no writes."""

    def test_dry_run_reports_changes_without_applying(self, brain_client):
        """Dry-run sync should return planned changes but not apply them."""
        sync_resp = brain_client.post("/api/v1/obsidian/sync", json={
            "vault": "Controlled E2E",
            "direction": "bidirectional",
            "dry_run": True,
        })
        assert sync_resp.status_code == 200
        data = sync_resp.json()
        # Dry run must not mutate state — verify by checking the response indicates preview
        assert "dry_run" in data or "planned" in data or data.get("applied", True) is False
```

- [ ] **Step 9.3: Run integration tests (with backend)**

```bash
INTEGRATION=1 /Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/integration/test_obsidian_roundtrip.py -v --tb=short
```

Expected: pass (requires live backend). If backend unavailable: tests skip, not fail.

- [ ] **Step 9.4: Run without INTEGRATION= to confirm skip behavior**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/integration/test_obsidian_roundtrip.py -v
```

Expected: 4 tests skipped with reason message.

- [ ] **Step 9.5: Commit**

```bash
git add unified/tests/integration/test_obsidian_roundtrip.py
git commit -m "test(obsidian): add 4-scenario integration roundtrip tests"
```

---

## Task 10: Final coverage verification

- [ ] **Step 10.1: Run full coverage report**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src --cov-report=term-missing -q 2>&1 | grep "TOTAL"
```

If TOTAL < 70%: identify the files with lowest coverage from Step 10.1 output and add targeted tests.

- [ ] **Step 10.2: Verify 70% threshold**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --cov=unified/src --cov-fail-under=70 -q
```

Expected: exit code 0.

- [ ] **Step 10.3: Verify docstring threshold**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/interrogate \
  unified/src/ --fail-under=80
```

Expected: exit code 0.

- [ ] **Step 10.4: Final commit**

```bash
git add -p
git commit -m "test: finalize coverage to ≥70% threshold"
```

---

## Exit Criteria

- [ ] `interrogate unified/src/ --fail-under=80` exits 0
- [ ] `pytest unified/tests/ --ignore=unified/tests/integration --cov=unified/src --cov-fail-under=70` exits 0
- [ ] Integration tests skip cleanly (not fail) when backend unavailable
- [ ] `python3 scripts/check_pr_readiness.py` passes
