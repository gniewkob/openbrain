# Iteration Report 2026-04-08 / 03

## Problem

The repo still had two MCP transports with diverging capability contracts. The stdio gateway had already been corrected, but the HTTP transport continued to advertise a narrower and structurally different capability surface.

## Evidence

- `unified/mcp-gateway/src/main.py` and `unified/src/mcp_transport.py` both expose `brain_capabilities`.
- Only the stdio gateway reflected the newer Obsidian capability split and explicit tool listing.
- Without alignment, clients could receive different operational answers depending on transport, even inside the same product.

## Decision

- Align the HTTP transport capability shape with the same explicit tool-list pattern used by the stdio gateway.
- Keep the HTTP transport scoped to its actual Obsidian surface (`obsidian_vaults`, `obsidian_read_note`, `obsidian_sync`) instead of pretending parity with the local-only gateway.

## Risk

- This iteration narrows capability drift, but it does not yet modernize the rest of the legacy HTTP transport behavior or endpoint choices.
- A later cleanup should decide whether `mcp_transport.py` remains first-class or is formally deprecated in favor of the dedicated gateway.

## Status

- Cross-transport capability drift: `fixed`
- Cross-transport behavior parity beyond capabilities: `deferred`
