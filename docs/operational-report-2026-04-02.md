# Operational Report: 2026-04-02

## Scope

This report captures the follow-up 360 audit closure after the 2026-04-01 remediation.
It covers request-tracing cleanup, CI/security guardrails, remaining transport parity gaps,
secret-scanning coverage, and shutdown lifecycle hygiene.

## Changes Completed

### 1. Request tracing integrity

- `RequestIDMiddleware` now clears request-scoped `structlog` context in `finally`.
- This prevents a failed request from leaking its `request_id` into later unrelated log events.

Files:
- `unified/src/main.py`
- `unified/tests/test_metrics.py`

### 2. CI guardrail refresh

- The unified smoke workflow no longer exports the removed `OPENBRAIN_DISABLE_DB_CONFIG_VALIDATION` flag.
- The `guardrails` job now installs `./unified` before running auth/db startup tests.
- Public-mode startup checks are now part of CI instead of relying only on module-import smoke.

Files:
- `.github/workflows/unified-smoke.yml`

### 3. Gateway / HTTP parity closure

- The stdio gateway `BrainMemory` model now includes V1 provenance fields:
  - `title`
  - `summary`
  - `source`
  - `governance`
- `brain_get` parity is now explicitly covered in the parity suite.
- Parity tests normalize `None` values so they validate semantic contract equivalence, not serializer differences.

Files:
- `unified/mcp-gateway/src/main.py`
- `unified/tests/test_transport_parity.py`
- `unified/mcp-gateway/tests/test_api_paths.py`

### 4. Secret scanning coverage expansion

- The committed-secret scanner now covers tracked text files more broadly.
- It additionally checks for:
  - `POSTGRES_PASSWORD`
  - generic `*_TOKEN` assignments
  - generic `*_SECRET` assignments
  - `Authorization: Bearer ...`
  - URL-embedded credentials in config-like and documentation-like files
- URL credential scanning is intentionally limited to sensible text/config suffixes to avoid noisy false positives in source code and tests.

Files:
- `scripts/check_no_committed_secrets.py`

### 5. Telemetry shutdown hygiene

- The periodic telemetry sync task is now cancelled and awaited during FastAPI lifespan shutdown.
- This avoids orphaned-task / pending-task noise and makes shutdown semantics cleaner.

Files:
- `unified/src/main.py`
- `unified/tests/test_metrics.py`

## Verification

Passed:

```bash
python3 scripts/check_no_committed_secrets.py
python3 scripts/check_compose_guardrails.py
docker exec -e PUBLIC_MODE=false -e PUBLIC_BASE_URL= openbrain-unified-server \
  python -m unittest tests.test_metrics tests.test_mcp_transport
PYTHONPATH=.:unified ./.venv/bin/python -m unittest unified.tests.test_transport_parity
./unified/mcp-gateway/.venv/bin/python -m unittest unified/mcp-gateway/tests/test_api_paths.py
```

Result:
- all targeted checks passed after the final parity normalization update

## Current Residual Risks

- `unified/src/main.py` and `unified/src/crud.py` remain large orchestration modules and still deserve decomposition for long-term maintainability.
- The monitoring bridge remains intentionally lightweight and local-first; it is not designed as a hardened general-purpose proxy tier.
- The MCP HTTP transport still creates a fresh backend `httpx.AsyncClient` per request, which is acceptable today but remains a throughput/efficiency tradeoff if usage increases substantially.

## Outcome

After this follow-up closure pass, the second 360 audit did not leave open findings in the categories of:
- code correctness
- functional parity
- immediate security posture
- CI/guardrail regressions
- high-signal operational hygiene
