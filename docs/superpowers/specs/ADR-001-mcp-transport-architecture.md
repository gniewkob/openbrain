# ADR-001: mcp_transport.py Architecture Decision

**Date:** 2026-04-11  
**Status:** Accepted  
**Author:** Codex (Phase 2 evaluation)

---

## Context

`unified/src/mcp_transport.py` (750 lines) was flagged in the 2026-04-11 audit as a potential architectural concern due to its size and dual-transport coexistence with `unified/mcp-gateway/src/main.py`.

Three options were evaluated:

| Option | Description |
|--------|-------------|
| A — Retire + redirect | Remove file, redirect callers to FastMCP transport |
| B — Modernize | Declare canonical, clean dead code, align with FastMCP patterns |
| C — Wrapper shim | Thin compatibility shim over legacy internals, deprecate |

## Analysis

### What `mcp_transport.py` is

`mcp_transport.py` **is** the FastMCP HTTP/SSE transport. It:
- Creates the `FastMCP` instance (`mcp = FastMCP(...)`)
- Registers all `brain_*` tools as FastMCP tools via decorators
- Exposes `mcp.streamable_http_app()` consumed by `combined.py` (the ASGI gateway)
- Uses `_SharedClient` / `_safe_req()` to proxy tool calls to the REST backend at `BRAIN_URL`

It is not a legacy wrapper or redundant layer.

### Why Option A is rejected

Contract guardrail tests enforce `combined.py must import mcp_transport` via:
- `scripts/check_mcp_transport_import_scope.py`
- `scripts/check_mcp_transport_mount_contract.py`

These guardrails are load-bearing CI checks. Retiring the file would require rewriting the guardrail contracts and the combined ASGI app simultaneously — high risk, no benefit.

### Why Option C is rejected

There is no legacy behavior to shim. The file already uses FastMCP idioms (decorator-based tool registration, `streamable_http_app()`). A shim layer would add indirection with no value.

### Why Option B is chosen

`mcp_transport.py` is the canonical HTTP/SSE transport. The correct action is:
1. Declare its role explicitly (this ADR)
2. Remove any dead code (none found — all helpers are called within the file)
3. Ensure transport parity tests remain green
4. Proceed to Phase 3 (docstrings/coverage)

## Decision

**Keep `mcp_transport.py` as the canonical HTTP/SSE FastMCP transport.**  
No structural changes. No dead code found.

## Dual-Transport Architecture (for reference)

```
Claude Desktop / ChatGPT
        ↓ HTTP/SSE
unified/src/mcp_transport.py  ← FastMCP tools (this file)
        ↓ HTTP
unified/src/  (REST backend, port 7010)

Claude Code / Codex / Gemini
        ↓ stdio
unified/mcp-gateway/src/main.py  ← stdio gateway
        ↓ HTTP
unified/src/  (REST backend, port 7010)
```

Both transports call the same REST backend. `mcp_transport.py` is the HTTP/SSE side.

## Consequences

- No changes to `mcp_transport.py`
- Contract guardrail tests remain passing
- Phase 2 closes: transport parity confirmed, dead code confirmed absent
