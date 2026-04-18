# Iteration Report 42 (2026-04-08)

## Problem

Obsidian integration behavior was covered by tests, but there was no dedicated
guardrail script enforcing feature-flag semantics and capabilities contract invariants.

## Evidence

- Local Obsidian tools must stay opt-in via `ENABLE_LOCAL_OBSIDIAN_TOOLS`.
- Capabilities payload must stay explicit (`obsidian`, legacy key, mode/status/tools).
- Manifest contract requires consistency between HTTP and local Obsidian tool sets.

## Decision

- Added `scripts/check_obsidian_contract.py` to enforce:
  - manifest consistency (`http_obsidian_tools` subset of `local_obsidian_tools`),
  - stdio local-tool gating (`_require_obsidian_local_tools_enabled()`),
  - capabilities shape presence in both transports.
- Added unit regression:
  - `unified/tests/test_obsidian_contract_guardrail.py`
- Wired script into `Unified Smoke Tests / guardrails`.

## Validation

- `python3 scripts/check_obsidian_contract.py` -> pass.
- `pytest -q unified/tests/test_obsidian_contract_guardrail.py unified/tests/test_mcp_transport.py unified/tests/test_capabilities_response_contract.py` -> pass.
- `python -m unittest tests.test_obsidian_tools tests.test_gateway_capabilities_response_contract -v` (from `unified/mcp-gateway`) -> pass.

## Risk

- Low: static policy script may require updates when Obsidian scope changes intentionally.

## Status

`fixed`

