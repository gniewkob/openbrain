# Execution Report 2026-04-08

## Current platform state

OpenBrain is now more truthful about its operational state and more internally consistent across transports. The most misleading behavior identified at the start of the work was capability reporting, not the core CRUD/search path itself.

## Confirmed issues

- `brain_capabilities` could over-report outage when the backend was reachable but degraded.
- The stdio gateway exposed more local Obsidian tools than it declared.
- The repo had transport-level capability drift between the dedicated MCP gateway and the HTTP transport.
- Local Obsidian gateway behavior had incomplete contract coverage in tests.

## Rejected or narrowed issues

- `updated_by` did not prove to be a broken write path in current code.
- The stronger conclusion is narrower: authenticated identity is the audit actor, while request-level `updated_by` is compatibility metadata and must not be treated as authoritative.

## Fixes implemented

- Stdio gateway now separates:
  - unreachable backend,
  - reachable but degraded backend,
  - explicit local Obsidian tool availability.
- Stdio gateway capabilities now list the full local Obsidian tool surface.
- Gateway test harness now mirrors the runtime import model for shared Obsidian code.
- Local Obsidian gateway tools now have contract coverage for:
  - opt-in gating,
  - endpoint path,
  - request payload shape.
- HTTP transport capability reporting now follows the same explicit-tool model for its own smaller Obsidian surface.
- PATCH endpoint tests now lock the audit rule that authenticated subject wins over spoofed `updated_by`.

## Deferred issues

- Real end-to-end Obsidian vault I/O against a live local environment.
- Broader modernization or retirement decision for `unified/src/mcp_transport.py`.
- Legacy endpoint cleanup in the HTTP transport beyond `brain_capabilities`.
- Search/data-noise cleanup and maintenance of historical test records.

## Residual operational risks

- Capability truthfulness is improved, but there are still two MCP-facing implementations in the repo.
- Live Obsidian behavior can still fail for environment-specific reasons even though the gateway contract is now much better covered.
- Historical docs in `docs/` still contain stale or superseded assumptions and should not be treated as authoritative without cross-checking code/tests.
