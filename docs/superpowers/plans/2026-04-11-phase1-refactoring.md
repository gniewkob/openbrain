# Phase 1: Complexity Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce cyclomatic complexity in `obsidian_sync.py` and `memory_writes.py` to max <15, average <10, with no regressions.

**Architecture:** TDD approach — write failing tests for new sub-functions first, then extract. Both targets are in `unified/src/`. The real complexity target in `memory_writes.py` is `_run_maintenance_inner()` (lines 788-940, ~152 lines), NOT `run_maintenance()` which is a thin timeout wrapper. `detect_changes()` should be verified first — it may already be below threshold after earlier refactoring.

**Tech Stack:** Python 3.13, pytest, radon (complexity checker)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `unified/src/memory_writes.py` | **Modify** | Extract 4 helper functions from `_run_maintenance_inner()` |
| `unified/src/obsidian_sync.py` | **Modify if needed** | Verify complexity first; extract helpers only if >15 |
| `unified/tests/test_maintenance_refactor.py` | **Create** | Tests for extracted maintenance helpers |
| `unified/tests/test_obsidian_sync_refactor.py` | **Create if needed** | Tests for extracted detect_changes helpers |

---

## Task 1: Measure current complexity

**Files:**
- Read: `unified/src/obsidian_sync.py`
- Read: `unified/src/memory_writes.py`

- [ ] **Step 1.1: Install radon if missing**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pip install radon -q
```

Expected: installs or already satisfied.

- [ ] **Step 1.2: Measure complexity of both files**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/radon cc \
  unified/src/obsidian_sync.py \
  unified/src/memory_writes.py \
  -s --min B
```

Expected output: list of functions with complexity grade B or higher.
Record the output — you need it to decide which functions to refactor.

- [ ] **Step 1.3: Evaluate detect_changes()**

If `detect_changes` shows complexity ≤ 15: **skip Task 2 entirely** (already acceptable).
If `detect_changes` shows complexity > 15: proceed to Task 2.

- [ ] **Step 1.4: Evaluate _run_maintenance_inner()**

If `_run_maintenance_inner` shows complexity ≤ 15: **skip Task 3 entirely** (already acceptable).
If `_run_maintenance_inner` shows complexity > 15: proceed to Task 3.

---

## Task 2: Refactor detect_changes() (skip if complexity ≤ 15)

**Files:**
- Modify: `unified/src/obsidian_sync.py`
- Create: `unified/tests/test_obsidian_sync_refactor.py`

The current `detect_changes()` (line 435) already delegates to helper functions. If it still exceeds threshold, the fix is to extract `_determine_change()` body into smaller named helpers.

- [ ] **Step 2.1: Write failing tests for planned extraction**

Create `unified/tests/test_obsidian_sync_refactor.py`:

```python
"""Tests for detect_changes sub-function contracts."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestDetectChangesContracts:
    """Verify that detect_changes produces correct SyncChange lists."""

    @pytest.fixture
    def engine(self):
        from src.obsidian_sync import SyncEngine
        return SyncEngine()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, engine):
        session = AsyncMock()
        adapter = AsyncMock()

        with patch("src.obsidian_sync._get_openbrain_memories", return_value={}), \
             patch("src.obsidian_sync._get_obsidian_files", return_value={}):
            engine.tracker = MagicMock()
            engine.tracker.get_all_states.return_value = []
            result = await engine.detect_changes(session, adapter, vault="test")
        assert result == []

    @pytest.mark.asyncio
    async def test_new_openbrain_memory_detected_as_change(self, engine):
        from src.obsidian_sync import SyncChange
        session = AsyncMock()
        adapter = AsyncMock()
        memory = MagicMock()
        memory.id = "mem-1"
        memory.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with patch("src.obsidian_sync._get_openbrain_memories", return_value={"test/note.md": memory}), \
             patch("src.obsidian_sync._get_obsidian_files", return_value={}), \
             patch("src.obsidian_sync._detect_new_openbrain_memories", return_value=[SyncChange(change_type="new_openbrain", memory_id="mem-1", obsidian_path="test/note.md", vault="test")]), \
             patch("src.obsidian_sync._detect_new_obsidian_files", return_value=[]):
            engine.tracker = MagicMock()
            engine.tracker.get_all_states.return_value = []
            result = await engine.detect_changes(session, adapter, vault="test")
        assert len(result) == 1
        assert result[0].memory_id == "mem-1"
```

- [ ] **Step 2.2: Run tests to confirm they fail correctly**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_obsidian_sync_refactor.py -v --tb=short
```

Expected: tests fail with import errors or assertion errors — NOT passing yet.

- [ ] **Step 2.3: Extract complexity from _determine_change() if needed**

Read `unified/src/obsidian_sync.py` lines 500-560 to understand `_determine_change()`.
If its complexity is the problem, split the method body into:
- `_handle_tracked_deletion(state, memory, obsidian_exists)` — handles when memory or obsidian file is gone
- `_handle_tracked_modification(state, memory_changed, obsidian_changed)` — handles conflict/update logic

Add both as private methods on `SyncEngine` class. Keep `_determine_change()` as the coordinator that calls them.

- [ ] **Step 2.4: Run tests to confirm they pass**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_obsidian_sync_refactor.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 2.5: Verify complexity is now ≤ 15**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/radon cc \
  unified/src/obsidian_sync.py -s --min B
```

Expected: no function above grade B (complexity > 10). Max allowed: 15.

- [ ] **Step 2.6: Run full test suite to check for regressions**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_obsidian_sync.py \
  unified/tests/test_obsidian_sync_refactor.py \
  -v --tb=short
```

Expected: all pass.

- [ ] **Step 2.7: Commit**

```bash
git add unified/src/obsidian_sync.py unified/tests/test_obsidian_sync_refactor.py
git commit -m "refactor(obsidian_sync): reduce detect_changes complexity below threshold"
```

---

## Task 3: Refactor _run_maintenance_inner()

**Files:**
- Modify: `unified/src/memory_writes.py` (lines 788-940)
- Create: `unified/tests/test_maintenance_refactor.py`

Current `_run_maintenance_inner()` does 3 things in one function:
1. Dedup processing (lines 799-851)
2. Owner normalization (lines 853-879)
3. Superseded link repair (lines 881-915)

Each becomes a private async function. `_run_maintenance_inner()` becomes the coordinator.

- [ ] **Step 3.1: Write failing tests for extracted helpers**

Create `unified/tests/test_maintenance_refactor.py`:

```python
"""Tests for _run_maintenance_inner sub-function contracts."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMaintenanceHelpers:
    """Verify extracted helper functions have correct signatures and return types."""

    @pytest.mark.asyncio
    async def test_process_duplicates_returns_actions_and_count(self):
        """_process_duplicates must return (actions_list, dedup_count)."""
        from src.memory_writes import _process_duplicates
        session = AsyncMock()
        # Simulate no duplicate groups
        session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        actions, count = await _process_duplicates(
            session=session, dedup_threshold=1, total=0, dry_run=True, actor="test"
        )
        assert isinstance(actions, list)
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_normalize_owners_returns_actions_and_count(self):
        """_normalize_owners must return (actions_list, owners_normalized_count)."""
        from src.memory_writes import _normalize_owners
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
        actions, count = await _normalize_owners(
            session=session, normalize_owners={}, dry_run=True
        )
        assert isinstance(actions, list)
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_fix_superseded_links_returns_actions_and_count(self):
        """_fix_superseded_links must return (actions_list, links_fixed_count)."""
        from src.memory_writes import _fix_superseded_links
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=lambda: []),  # active_ids query
                MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # superseded query
            ]
        )
        actions, count = await _fix_superseded_links(
            session=session, dry_run=True
        )
        assert isinstance(actions, list)
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_run_maintenance_inner_integrates_all_helpers(self):
        """_run_maintenance_inner must produce a MaintenanceReport."""
        from src.memory_writes import _run_maintenance_inner
        from src.schemas import MaintenanceRequest, MaintenanceReport
        session = AsyncMock()
        # Minimal mock: total count query returns 0
        session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0))
        req = MaintenanceRequest(dry_run=True, dedup_threshold=0)
        report = await _run_maintenance_inner(session=session, req=req, actor="test")
        assert isinstance(report, MaintenanceReport)
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_maintenance_refactor.py -v --tb=short
```

Expected: `ImportError` — functions `_process_duplicates`, `_normalize_owners`, `_fix_superseded_links` do not exist yet.

- [ ] **Step 3.3: Extract _process_duplicates()**

In `unified/src/memory_writes.py`, add this private async function BEFORE `_run_maintenance_inner()` (insert at approximately line 787):

```python
async def _process_duplicates(
    session: AsyncSession,
    dedup_threshold: int,
    total: int,
    dry_run: bool,
    actor: str,
) -> tuple[list[MaintenanceAction], int]:
    """Find and mark/remove exact duplicate memories. Returns (actions, dedup_count)."""
    actions: list[MaintenanceAction] = []
    dedup_count = 0

    if dedup_threshold <= 0 or total <= 1:
        return actions, dedup_count

    dup_groups_stmt = (
        select(Memory.content_hash, Memory.entity_type, Memory.domain)
        .where(Memory.status == "active", Memory.content_hash.isnot(None))
        .group_by(Memory.content_hash, Memory.entity_type, Memory.domain)
        .having(func.count(Memory.id) > 1)
    )
    dup_groups = (await session.execute(dup_groups_stmt)).all()

    for content_hash, entity_type, domain in dup_groups:
        members_stmt = (
            select(Memory)
            .where(
                Memory.content_hash == content_hash,
                Memory.entity_type == entity_type,
                Memory.domain == domain,
                Memory.status == "active",
            )
            .order_by(Memory.created_at.asc())
        )
        members = (await session.execute(members_stmt)).scalars().all()
        canonical = members[0]
        for duplicate in members[1:]:
            dedup_count += 1
            actions.append(
                MaintenanceAction(
                    action="dedup",
                    memory_id=duplicate.id,
                    detail=f"Exact duplicate of {canonical.id}",
                )
            )
            if not dry_run:
                if _requires_append_only(duplicate.domain, duplicate.entity_type):
                    duplicate.status = STATUS_DUPLICATE
                    duplicate.metadata_ = {
                        **(duplicate.metadata_ or {}),
                        "duplicate_of": canonical.id,
                        "remediated_at": datetime.now().isoformat(),
                    }
                    actions.append(
                        MaintenanceAction(
                            action="dedup_remediate",
                            memory_id=duplicate.id,
                            detail=(
                                f"Exact duplicate of {canonical.id} "
                                f"marked as duplicate via "
                                f"governance-safe remediation (append-only)"
                            ),
                        )
                    )
                else:
                    duplicate.status = STATUS_SUPERSEDED
                    duplicate.superseded_by = canonical.id

    return actions, dedup_count
```

- [ ] **Step 3.4: Extract _normalize_owners()**

Add after `_process_duplicates()`:

```python
async def _normalize_owners(
    session: AsyncSession,
    normalize_owners: dict[str, str],
    dry_run: bool,
) -> tuple[list[MaintenanceAction], int]:
    """Normalize owner names in memories. Returns (actions, owners_normalized_count)."""
    actions: list[MaintenanceAction] = []
    owners_norm = 0

    if not normalize_owners:
        return actions, owners_norm

    old_owners = list(normalize_owners.keys())
    norm_stmt = select(Memory).where(
        Memory.status == "active", Memory.owner.in_(old_owners)
    )
    norm_memories = (await session.execute(norm_stmt)).scalars().all()
    for memory in norm_memories:
        new_owner = normalize_owners[memory.owner]
        actions.append(
            MaintenanceAction(
                action="normalize_owner",
                memory_id=memory.id,
                detail=f"'{memory.owner}' -> '{new_owner}'",
            )
        )
        if not dry_run:
            if _requires_append_only(memory.domain, memory.entity_type):
                actions.append(
                    MaintenanceAction(
                        action="policy_skip",
                        memory_id=memory.id,
                        detail="Skipped owner normalization for append-only memory",
                    )
                )
                continue
            memory.owner = new_owner
            owners_norm += 1

    return actions, owners_norm
```

- [ ] **Step 3.5: Extract _fix_superseded_links()**

Add after `_normalize_owners()`:

```python
async def _fix_superseded_links(
    session: AsyncSession,
    dry_run: bool,
) -> tuple[list[MaintenanceAction], int]:
    """Repair broken superseded_by links. Returns (actions, links_fixed_count)."""
    actions: list[MaintenanceAction] = []
    links_fixed = 0

    active_ids_result = await session.execute(
        select(Memory.id).where(Memory.status == "active")
    )
    active_ids = {row[0] for row in active_ids_result.all()}
    superseded_stmt = select(Memory).where(
        Memory.superseded_by.isnot(None), Memory.status == "superseded"
    )
    superseded_memories = (await session.execute(superseded_stmt)).scalars().all()
    for memory in superseded_memories:
        if memory.superseded_by and memory.superseded_by not in active_ids:
            links_fixed += 1
            actions.append(
                MaintenanceAction(
                    action="fix_link",
                    memory_id=memory.id,
                    detail=f"superseded_by {memory.superseded_by} not found in active",
                )
            )
            if not dry_run:
                if _requires_append_only(memory.domain, memory.entity_type):
                    actions.append(
                        MaintenanceAction(
                            action="policy_skip",
                            memory_id=memory.id,
                            detail="Skipped supersession link repair for append-only memory",
                        )
                    )
                    continue
                memory.superseded_by, memory.status = None, "active"

    return actions, links_fixed
```

- [ ] **Step 3.6: Rewrite _run_maintenance_inner() as coordinator**

Replace the body of `_run_maintenance_inner()` (keep the signature, replace everything inside):

```python
async def _run_maintenance_inner(
    session: AsyncSession, req: MaintenanceRequest, actor: str = "agent"
) -> MaintenanceReport:
    total_result = await session.execute(
        select(func.count(Memory.id)).where(Memory.status == "active")
    )
    total = total_result.scalar_one()

    dup_actions, dedup_count = await _process_duplicates(
        session=session,
        dedup_threshold=req.dedup_threshold,
        total=total,
        dry_run=req.dry_run,
        actor=actor,
    )
    owner_actions, owners_norm = await _normalize_owners(
        session=session,
        normalize_owners=req.normalize_owners or {},
        dry_run=req.dry_run,
    )
    link_actions, links_fixed = await _fix_superseded_links(
        session=session,
        dry_run=req.dry_run,
    )

    actions = dup_actions + owner_actions + link_actions
    report = MaintenanceReport(
        dry_run=req.dry_run,
        actions=actions,
        total_scanned=total,
        dedup_found=dedup_count,
        owners_normalized=owners_norm,
        links_fixed=links_fixed,
    )

    if req.dry_run:
        await session.commit()
        return report

    audit_entry = AuditLog(
        operation="maintain",
        tool_name="memory.maintain",
        memory_id=None,
        actor=actor,
        domain=None,
        tenant_id=None,
        changes={
            "dedup_count": dedup_count,
            "owners_normalized": owners_norm,
            "links_fixed": links_fixed,
            "actions_count": len(actions),
        },
    )
    session.add(audit_entry)
    await session.commit()
    return report
```

> Note: Read the original `_run_maintenance_inner()` audit log block (after line 930) to ensure the `AuditLog` fields above match the existing schema exactly.

- [ ] **Step 3.7: Run tests to confirm they pass**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_maintenance_refactor.py \
  unified/tests/test_maintenance_timeout.py \
  unified/tests/test_memory_writes.py \
  -v --tb=short
```

Expected: all pass.

- [ ] **Step 3.8: Verify complexity is now ≤ 15**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/radon cc \
  unified/src/memory_writes.py -s --min B
```

Expected: `_run_maintenance_inner` no longer appears above grade B.

- [ ] **Step 3.9: Commit**

```bash
git add unified/src/memory_writes.py unified/tests/test_maintenance_refactor.py
git commit -m "refactor(memory_writes): extract _run_maintenance_inner into focused helpers"
```

---

## Task 4: Final complexity verification

- [ ] **Step 4.1: Run full complexity report**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/radon cc \
  unified/src/ -s -a --min B
```

Expected:
- No function exceeds complexity 15 (grade D or higher)
- Average complexity < 10

- [ ] **Step 4.2: Run full test suite**

```bash
/Users/gniewkob/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration \
  --tb=short -q
```

Expected: all tests pass, no regressions.

- [ ] **Step 4.3: Final commit if anything remaining**

```bash
git add -p  # review any remaining changes
git commit -m "refactor: final complexity cleanup pass"
```

---

## Exit Criteria

- [ ] `radon cc unified/src/ -s -a` — Average < 10, max function complexity ≤ 15
- [ ] All tests pass (no regressions)
- [ ] `python3 scripts/check_pr_readiness.py` passes
