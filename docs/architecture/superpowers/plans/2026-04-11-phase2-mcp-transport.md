# Phase 2: mcp_transport.py Architecture Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the deferred architectural decision on `unified/src/mcp_transport.py` — map usage, choose an approach, implement it, and eliminate dual-transport parity debt.

**Architecture:** OpenBrain has two MCP transport implementations: `unified/src/mcp_transport.py` (HTTP/SSE transport, 765 lines, served via `combined.py`) and `unified/mcp-gateway/src/main.py` (stdio gateway for Claude Code/Codex). The stdio gateway is the primary transport for agentic clients. The HTTP transport serves Claude Desktop and ChatGPT. The decision is whether to keep both maintained in parallel, retire one, or consolidate logic.

**Tech Stack:** Python 3.13, FastMCP, httpx, pytest

---

## File Map

| File | Action |
|------|--------|
| `unified/src/mcp_transport.py` | **Modify or retire** (depends on decision) |
| `unified/mcp-gateway/src/main.py` | **Possibly modify** (if consolidating) |
| `unified/tests/test_transport_parity.py` | **Update** (reflect post-decision state) |
| `unified/tests/test_combined_transport_contract.py` | **Update** |
| `docs/adr/` | **Create** ADR documenting decision |

---

## Task 1: Map all usages of mcp_transport.py

**Files:**
- Read: `unified/src/mcp_transport.py`
- Read: `unified/src/combined.py`

- [ ] **Step 1.1: Find all imports of mcp_transport**

```bash
grep -rn "mcp_transport\|from .mcp_transport\|import mcp_transport" \
  unified/src/ unified/mcp-gateway/ unified/tests/ --include="*.py"
```

Record all results. This is the complete call-site map.

- [ ] **Step 1.2: Count lines and understand entry points**

```bash
wc -l unified/src/mcp_transport.py unified/mcp-gateway/src/main.py
grep -n "^async def \|^def " unified/src/mcp_transport.py | head -40
grep -n "^async def \|^def " unified/mcp-gateway/src/main.py | head -40
```

Note: how many public `brain_*` tools are in each file?

- [ ] **Step 1.3: Check combined.py routing**

```bash
grep -n "mcp_transport\|FastMCP\|mount\|route" unified/src/combined.py | head -30
```

Understand: does `combined.py` mount `mcp_transport`'s FastMCP app? Or does it register tools separately?

- [ ] **Step 1.4: Check which clients use HTTP transport vs stdio**

```bash
grep -rn "BRAIN_URL\|/sse\|/mcp\|transport.*http\|transport.*sse" \
  unified/ docs/ --include="*.yml" --include="*.json" --include="*.md" | head -20
```

Record which systems connect via HTTP (Claude Desktop, ChatGPT) vs stdio (Claude Code, Codex).

---

## Task 2: Document decision

**Files:**
- Create: `docs/adr/ADR-001-mcp-transport-architecture.md`

- [ ] **Step 2.1: Evaluate three options based on Task 1 findings**

Read Task 1 results and evaluate:

**Option A — Retire HTTP transport (`mcp_transport.py`)**
- When to choose: if no active HTTP clients (Claude Desktop, ChatGPT) are connected, or if they can be migrated to stdio
- Risk: breaks any live HTTP-connected client
- Gain: -765 lines, zero parity debt

**Option B — Modernize `mcp_transport.py` in-place**
- When to choose: HTTP clients are active and must stay; but the file is doing too much
- Action: split into `mcp_http_tools.py` (tool implementations) + `mcp_http_server.py` (server/routing)
- Risk: medium refactor effort; parity tests must be updated
- Gain: better separation of concerns, parity debt reduced

**Option C — Thin shim (recommended if HTTP clients are active)**
- When to choose: HTTP clients are active; tool logic is already well-tested in gateway
- Action: extract shared tool logic into `unified/src/brain_tools.py`; both transports import from it
- Risk: larger refactor; requires careful interface design
- Gain: single source of truth for tool logic, eliminates parity drift permanently

- [ ] **Step 2.2: Create ADR file**

Create `docs/adr/ADR-001-mcp-transport-architecture.md`:

```markdown
# ADR-001: MCP Transport Architecture Decision

**Date:** 2026-04-11 (update with actual date)
**Status:** Accepted
**Deciders:** [fill in]

## Context

OpenBrain has two MCP transport implementations:
- `unified/src/mcp_transport.py` (HTTP/SSE, 765 lines) — serves Claude Desktop, ChatGPT
- `unified/mcp-gateway/src/main.py` (stdio) — serves Claude Code, Codex

Maintaining both in parallel creates parity drift risk and doubles the maintenance surface.

## Decision

[FILL IN: A, B, or C — based on Task 1 findings]

**Chosen option:** [A / B / C]

**Rationale:**
- Active HTTP clients: [yes/no — list them]
- Parity test debt: [describe current state]
- Migration feasibility: [easy/hard — why]

## Consequences

**Positive:**
- [list]

**Negative / Risks:**
- [list]

**Mitigations:**
- [list]
```

Fill in all bracketed sections based on Task 1 analysis.

- [ ] **Step 2.3: Commit the ADR before implementing**

```bash
git add docs/adr/ADR-001-mcp-transport-architecture.md
git commit -m "docs(adr): add ADR-001 mcp transport architecture decision"
```

---

## Task 3: Implement chosen option

Follow the sub-task matching your decision from Task 2.

---

### Task 3A: Retire HTTP transport (if Option A chosen)

- [ ] **Step 3A.1: Write a deprecation test before removing**

Add to `unified/tests/test_transport_parity.py`:

```python
def test_http_transport_is_retired():
    """Confirm mcp_transport.py no longer exports brain_* tools."""
    import importlib
    import sys
    # After retirement, mcp_transport should either not exist
    # or export zero brain_* functions
    try:
        mod = importlib.import_module("src.mcp_transport")
        brain_tools = [k for k in dir(mod) if k.startswith("brain_")]
        assert brain_tools == [], f"Expected no brain_ tools, found: {brain_tools}"
    except ModuleNotFoundError:
        pass  # Fully retired — acceptable
```

- [ ] **Step 3A.2: Run test to confirm it fails**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_transport_parity.py::test_http_transport_is_retired -v
```

Expected: FAIL (module exists with brain_ tools).

- [ ] **Step 3A.3: Remove mcp_transport.py registration from combined.py**

Read `unified/src/combined.py`. Find where `mcp_transport` is imported or its FastMCP app is mounted. Remove that registration. Leave a `# HTTP transport retired (ADR-001)` comment.

- [ ] **Step 3A.4: Delete mcp_transport.py**

```bash
git rm unified/src/mcp_transport.py
```

- [ ] **Step 3A.5: Fix any remaining imports**

```bash
grep -rn "mcp_transport" unified/ --include="*.py"
```

Remove or update any remaining imports.

- [ ] **Step 3A.6: Run retirement test**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_transport_parity.py::test_http_transport_is_retired -v
```

Expected: PASS.

- [ ] **Step 3A.7: Run full test suite**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/ --ignore=unified/tests/integration --tb=short -q
```

Expected: all pass. If parity tests fail because they check HTTP transport behavior, update them to reflect retired state.

- [ ] **Step 3A.8: Commit**

```bash
git add -A
git commit -m "feat(transport): retire mcp_transport.py HTTP transport (ADR-001)"
```

---

### Task 3B: Modernize in-place (if Option B chosen)

- [ ] **Step 3B.1: Split mcp_transport.py into two files**

Create `unified/src/mcp_http_tools.py` — tool implementation functions only (brain_search, brain_store, etc).
Modify `unified/src/mcp_transport.py` — keep only server setup, routing, middleware (_safe_req, _client, FastMCP registration).

Move each `async def brain_*` function to `mcp_http_tools.py`. Import them back in `mcp_transport.py`.

- [ ] **Step 3B.2: Run parity tests after split**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_transport_parity.py \
  unified/tests/test_combined_transport_contract.py \
  -v --tb=short
```

Expected: all pass (behavior unchanged).

- [ ] **Step 3B.3: Verify file sizes are more manageable**

```bash
wc -l unified/src/mcp_transport.py unified/src/mcp_http_tools.py
```

Expected: neither file exceeds 400 lines.

- [ ] **Step 3B.4: Commit**

```bash
git add unified/src/mcp_transport.py unified/src/mcp_http_tools.py
git commit -m "refactor(transport): split mcp_transport into server + tools (ADR-001 Option B)"
```

---

### Task 3C: Shared tool logic shim (if Option C chosen)

- [ ] **Step 3C.1: Create unified/src/brain_tools.py**

Extract the core request/response logic from `mcp_transport.py` that is duplicated in `mcp-gateway/src/main.py` into a new shared module `unified/src/brain_tools.py`. This module should contain pure functions that take `session`/`http_client` parameters rather than relying on module-level state.

- [ ] **Step 3C.2: Update both transports to import from brain_tools.py**

Both `mcp_transport.py` and `mcp-gateway/src/main.py` delegate to `brain_tools.py` functions.

- [ ] **Step 3C.3: Run parity tests**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_transport_parity.py \
  unified/tests/test_combined_transport_contract.py \
  -v --tb=short
```

Expected: all pass.

- [ ] **Step 3C.4: Commit**

```bash
git add unified/src/brain_tools.py unified/src/mcp_transport.py unified/mcp-gateway/src/main.py
git commit -m "refactor(transport): extract shared brain_tools module (ADR-001 Option C)"
```

---

## Task 4: Final verification

- [ ] **Step 4.1: Run transport parity tests**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_transport_parity.py \
  unified/tests/test_combined_transport_contract.py \
  unified/tests/test_mcp_transport.py \
  -v --tb=short
```

Expected: all pass.

- [ ] **Step 4.2: Run PR readiness**

```bash
python3 scripts/check_pr_readiness.py
```

Expected: passes.

---

## Exit Criteria

- [ ] ADR-001 committed to `docs/adr/`
- [ ] Chosen option implemented
- [ ] `test_transport_parity.py` and `test_combined_transport_contract.py` pass
- [ ] `python3 scripts/check_pr_readiness.py` passes
- [ ] No dead code remains from retired/refactored paths
