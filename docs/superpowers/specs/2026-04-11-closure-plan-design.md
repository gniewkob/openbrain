# OpenBrain — Closure Plan Design

**Date:** 2026-04-11  
**Status:** Approved  
**Executor:** Codex (sequential, step-by-step, backlog-driven)  
**Scope:** Close all open issues and risks identified in the 2026-04-11 audit

---

## Overview

Gate-based execution in 4 sequential phases. Each phase has explicit entry/exit criteria and a backlog of tasks Codex works through one at a time. No phase begins until the previous one passes its exit criteria.

```
Faza 0: MERGE GATE          → master is clean and up to date
Faza 1: REFAKTORING          → complexity reduced, tests green
Faza 2: ARCHITEKTURA         → mcp_transport.py decision implemented
Faza 3: JAKOŚĆ KODU          → docstrings ≥80%, coverage ≥70%
```

---

## Faza 0: Merge Gate

**Entry criteria:**
- Branch `codex/include-test-data-contract` exists with clean CI

**Exit criteria:**
- Branch merged to `master`
- `master` smoke tests pass
- Branch deleted

**Backlog:**
- [ ] Run `python3 scripts/check_pr_readiness.py` — must pass
- [ ] Run `python3 scripts/check_release_gate.py` — must pass
- [ ] Merge `codex/include-test-data-contract` → `master` (merge commit with summary)
- [ ] Delete source branch
- [ ] Run smoke tests on `master` to verify clean state

---

## Faza 1: Refaktoring Złożoności

**Entry criteria:**
- `master` clean after Faza 0

**Exit criteria:**
- `radon cc src/ -s -a` — Average Complexity < 10, max < 15
- All existing tests pass

### 1a — `detect_changes()` in `unified/src/obsidian_sync.py`

Current: 132 lines, cyclomatic complexity ~21

**Backlog:**
- [ ] Write failing unit tests for planned sub-functions (TDD)
- [ ] Extract `_detect_vault_changes(vault)` (~40 lines)
- [ ] Extract `_identify_conflicts(changes)` (~40 lines)
- [ ] Extract `_build_sync_result(changes, conflicts)` (~30 lines)
- [ ] Verify complexity with `radon cc src/obsidian_sync.py -s`
- [ ] Verify all tests pass

### 1b — `run_maintenance()` in `unified/src/memory_writes.py`

Current: 113 lines, cyclomatic complexity ~20

**Backlog:**
- [ ] Write failing unit tests for planned sub-functions (TDD)
- [ ] Extract `_collect_maintenance_candidates()`
- [ ] Extract `_process_duplicates()`
- [ ] Extract `_process_policy_skips()`
- [ ] Extract `_build_maintenance_report()`
- [ ] Verify complexity with `radon cc src/memory_writes.py -s`
- [ ] Verify all tests pass

---

## Faza 2: Architektura mcp_transport.py

**Entry criteria:**
- Faza 1 complete

**Exit criteria:**
- Decision implemented
- Transport parity tests green
- Dead code removed

**Decision options (Codex evaluates and picks one):**
- **A) Retire + redirect** — remove `mcp_transport.py`, redirect all callers to FastMCP transport
- **B) Modernize** — rewrite internals to align with FastMCP patterns, keep public interface
- **C) Wrapper shim** — wrap legacy behavior behind a thin compatibility shim, deprecate over time

**Backlog:**
- [ ] Grep for all usages of `mcp_transport.py` across codebase
- [ ] Use `find_referencing_symbols` to map all call sites
- [ ] Evaluate options A/B/C against current usage patterns
- [ ] Document decision with rationale in a comment or ADR
- [ ] Implement chosen option
- [ ] Update transport parity tests (`test_transport_parity.py`, `test_combined_transport_contract.py`)
- [ ] Remove dead code and unused imports
- [ ] Verify all tests pass

---

## Faza 3: Jakość Kodu

**Entry criteria:**
- Faza 2 complete

**Exit criteria:**
- `interrogate src/ --fail-under=80` passes
- `pytest --cov=src --cov-fail-under=70` passes

### 3a — Docstrings

Priority modules (in order):

**Backlog:**
- [ ] `src/auth.py` — add docstrings to 15 public functions
- [ ] `src/api/v1/*.py` — add docstrings to ~20 endpoint functions
- [ ] `src/memory_reads.py` — add docstrings to 12 functions
- [ ] `src/memory_writes.py` — add docstrings to 10 functions
- [ ] Remaining modules until `interrogate src/ --fail-under=80` passes
- [ ] Verify: `interrogate src/ --fail-under=80`

### 3b — Test Coverage

**Backlog:**
- [ ] Run `pytest --cov=src --cov-report=term-missing -q` — identify gaps
- [ ] Add tests for `obsidian_sync.py` (highest priority, critical path)
- [ ] Add tests for `memory_reads.py`
- [ ] Add tests for `repositories/`
- [ ] Add integration tests for Obsidian: export, import, conflict resolution, dry-run
- [ ] Verify: `pytest --cov=src --cov-fail-under=70` passes

---

## Risks and Mitigations

| Risk | Phase | Mitigation |
|------|-------|------------|
| `detect_changes()` refactor breaks Obsidian sync | 1a | Write E2E integration tests before refactoring |
| mcp_transport.py retire breaks live transport | 2 | Map all call sites before deciding; run parity tests after |
| Docstring generation introduces inaccurate docs | 3a | Review generated docstrings against actual function behavior |
| Coverage <70% after targeted tests | 3b | Prioritize `obsidian_sync.py` and `memory_reads.py` — highest gap |

---

## Out of Scope

- Q2 roadmap Faza 5 (type hints, structured logging, SQL optimization) — deferred post-Q2
- Additional doc consolidation outside governance stream
- New features or API changes
