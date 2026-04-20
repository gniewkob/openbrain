# Phase 0: Merge Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge branch `codex/include-test-data-contract` into `master` cleanly and verify the result.

**Architecture:** Run pre-merge readiness scripts, perform the merge, verify smoke tests on master. No code changes — this is purely a gate/integration step.

**Tech Stack:** git, Python 3.13, pytest

---

## File Map

| File | Action |
|------|--------|
| (none) | No files are created or modified — this plan is git operations only |

---

## Task 1: Pre-merge verification

**Files:**
- Run: `scripts/check_pr_readiness.py`
- Run: `scripts/check_release_gate.py`

- [ ] **Step 1.1: Run PR readiness check**

```bash
python3 scripts/check_pr_readiness.py
```

Expected output: `PR readiness bundle passed.`
If it fails: read the output, fix the reported issue, re-run before proceeding.

- [ ] **Step 1.2: Run release gate check**

```bash
python3 scripts/check_release_gate.py
```

Expected output: gate reports branch protected, no missing checks.
If it fails: investigate and fix before proceeding.

- [ ] **Step 1.3: Verify CI is green on current branch**

```bash
git status
git log --oneline -3
```

Confirm: working tree is clean, last commit is on `codex/include-test-data-contract`.

---

## Task 2: Merge to master

**Files:**
- Git operations only

- [ ] **Step 2.1: Switch to master and pull latest**

```bash
git checkout master
git pull origin master
```

Expected: `Already up to date.` or fast-forward.

- [ ] **Step 2.2: Merge the branch**

```bash
git merge --no-ff codex/include-test-data-contract -m "$(cat <<'EOF'
merge: close codex/include-test-data-contract → master

Closes 63-commit governance/contract hardening stream:
- Test-data hygiene report + cleanup endpoint
- Admin bounds/endpoint contract parity guardrails
- Hidden test-data monitoring + alerting
- Health fallback (/api/v1/readyz)
- Capabilities metadata v2.4.0
EOF
)"
```

Expected: merge commit created, no conflicts.
If there are conflicts: resolve them, `git add` affected files, `git commit`.

- [ ] **Step 2.3: Verify merge commit on master**

```bash
git log --oneline -5
```

Expected: merge commit is HEAD on master.

---

## Task 3: Post-merge verification

**Files:**
- Run: `unified/tests/` (smoke subset)

- [ ] **Step 3.1: Run smoke tests**

```bash
/Users/<user>/Repos/openbrain/unified/.venv/bin/pytest \
  unified/tests/test_startup_smoke.py \
  unified/tests/test_contract_parity.py \
  unified/tests/test_secret_scan.py \
  -v --tb=short
```

Expected: all pass.

- [ ] **Step 3.2: Run PR readiness on master**

```bash
python3 scripts/check_pr_readiness.py
```

Expected: `PR readiness bundle passed.`

- [ ] **Step 3.3: Delete source branch**

```bash
git branch -d codex/include-test-data-contract
git push origin --delete codex/include-test-data-contract
```

Expected: branch deleted locally and remotely.

- [ ] **Step 3.4: Push master**

```bash
git push origin master
```

Expected: pushed cleanly.

---

## Exit Criteria

- [ ] `git branch` does not show `codex/include-test-data-contract`
- [ ] `git log --oneline -1` on master shows the merge commit
- [ ] All smoke tests pass on master
