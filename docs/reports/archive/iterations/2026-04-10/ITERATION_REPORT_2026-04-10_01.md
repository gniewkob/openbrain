# Iteration Report — 2026-04-10 (01)

- stream: availability / local+ngrok connectivity stabilization
- status: fixed

## Problem

After introducing Docker/ngrok and gateway pathing changes, local and public connectivity failed. The immediate startup blocker was a gateway import-time crash after contract-loader refactor.

## Evidence

- `runtime_limits.py` and `capabilities_manifest.py` referenced `Any` without import (import-time failure).
- Contract parity guardrails assumed path-variable loaders only (`manifest_path`, `contract_path`, `path`) and failed after `load_contract(...)` migration.
- `make pr-readiness` initially failed on parity guardrails despite otherwise valid refactor intent.

## Decision

- Fixed gateway startup blocker:
  - restored `Any` imports in `unified/mcp-gateway/src/runtime_limits.py` and `.../capabilities_manifest.py`
- Kept robust contract-loader refactor and made guardrails implementation-agnostic:
  - updated parity scripts to validate same contract filename semantics (instead of hardcoding path-variable AST shape)
  - retained strict parity on validation logic/defaults
- Verified module syntax/importability and full local readiness bundle.

## Risk

- Low/medium: this change batch modifies startup + configuration paths for public exposure.
- Mitigation: full local guardrail + parity + contract readiness checks passed before PR.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_manifest_parity_guardrail.py unified/tests/test_capabilities_metadata_parity_guardrail.py unified/tests/test_request_runtime_parity_guardrail.py unified/tests/test_runtime_limits.py`
- `python3 -m py_compile unified/mcp-gateway/src/contract_loader.py unified/mcp-gateway/src/runtime_limits.py unified/mcp-gateway/src/capabilities_manifest.py unified/mcp-gateway/src/capabilities_metadata.py unified/mcp-gateway/src/request_builders.py unified/mcp-gateway/src/http_error_adapter.py unified/mcp-gateway/src/memory_paths.py unified/mcp-gateway/src/mcp_http.py`
- `make pr-readiness`

## Files

- `docker-compose.unified.yml`
- `unified/mcp-gateway/Dockerfile`
- `unified/mcp-gateway/src/contract_loader.py`
- `unified/mcp-gateway/src/request_builders.py`
- `unified/mcp-gateway/src/runtime_limits.py`
- `unified/mcp-gateway/src/capabilities_manifest.py`
- `unified/mcp-gateway/src/capabilities_metadata.py`
- `unified/mcp-gateway/src/http_error_adapter.py`
- `unified/mcp-gateway/src/memory_paths.py`
- `unified/mcp-gateway/src/mcp_http.py`
- `unified/src/main.py`
- `scripts/check_capabilities_manifest_parity.py`
- `scripts/check_capabilities_metadata_parity.py`
- `scripts/check_request_runtime_parity.py`
