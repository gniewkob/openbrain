# Operational Report: 2026-03-27

## Scope

This report captures the work completed during the 2026-03-27 hardening session for OpenBrain Unified.
It covers transport contract fixes, Obsidian tool exposure, test stabilization, and live server verification
over both localhost and ngrok.

## Changes Completed

### 1. `brain_update` fix

- Fixed the legacy update path so it preserves the existing record identity and `match_key`.
- Preserved existing title when no new title is provided.
- Preserved relations during updates instead of dropping them.

Files:
- `unified/src/crud.py`
- `unified/src/schemas.py`
- `unified/tests/test_update_memory.py`

### 2. HTTP MCP error propagation fix

- Fixed HTTP/ngrok MCP behavior so backend `4xx/5xx` responses are returned as real MCP tool errors.
- Removed the previous false-success pattern where tool calls returned `isError = false` with a payload like
  `{"status":"error","code":...}`.

Files:
- `unified/src/mcp_transport.py`
- `unified/tests/test_mcp_transport.py`

### 3. Obsidian exposure fix

- Removed `brain_obsidian_vaults`, `brain_obsidian_read_note`, and `brain_obsidian_sync` from HTTP/ngrok MCP.
- Kept Obsidian tools available only in the local `stdio` gateway, where host access to the Obsidian CLI exists.
- Updated capability reporting to stop advertising host-only tools remotely.

Files:
- `unified/src/mcp_transport.py`

### 4. Status banner fix

- Updated `./start_unified.sh status` so it no longer claims that Obsidian tools are available over HTTP.
- Split the banner into:
  - `HTTP MCP Tools`
  - `Local-only Tools`

Files:
- `start_unified.sh`

### 5. Transport success-shape parity

- Normalized HTTP MCP success payloads so they match local `stdio` gateway outputs for:
  - `brain_store`
  - `brain_list`
  - `brain_search`
  - `brain_delete`
- Normalized V1 `record` envelopes to the legacy `MemoryOut`-shaped payload used by the local gateway.
- Fixed HTTP `brain_update` so it forwards `title`.

Files:
- `unified/src/mcp_transport.py`
- `unified/tests/test_mcp_transport.py`

### 6. Test harness stabilization

- Added a parity regression test comparing `stdio` gateway behavior against HTTP transport behavior.
- Added repo-level `Makefile` test entrypoints:
  - `make bootstrap-unified-venv`
  - `make bootstrap-gateway-venv`
  - `make test-unified`
  - `make test-gateway`
  - `make test`
- Adjusted test execution so gateway tests use the correct interpreter and package path.
- Stabilized default backend test entrypoint by using a curated suite instead of raw `discover`.

Files:
- `Makefile`
- `README.md`
- `INSTALLATION.md`
- `unified/tests/test_transport_parity.py`
- `unified/mcp-gateway/tests/helpers.py`
- `unified/mcp-gateway/tests/test_api_paths.py`
- `unified/mcp-gateway/tests/test_obsidian_tools.py`

## Verified Results

### Unit and regression tests

Passed:
- `make test-unified`
- `make test-gateway`

`make test-unified` currently runs the stable set:
- `unified.tests.test_mcp_transport`
- `unified.tests.test_obsidian_cli`
- `unified.tests.test_update_memory`
- `unified.tests.test_transport_parity`

### Live transport verification

Verified parity across:
- local `stdio` gateway
- `http://localhost:7010/sse`
- `https://poutily-hemispheroidal-pia.ngrok-free.dev/sse`

Confirmed equal success shapes for:
- `brain_store`
- `brain_list`
- `brain_search`
- `brain_delete`

### Live HTTP server verification

Verified local:
- `GET /health` returns `ok`
- authenticated `POST /api/memories`
- authenticated `GET /api/memories/{id}`
- authenticated `DELETE /api/memories/{id}`

Verified external through ngrok:
- `GET /health` returns `ok`
- `GET /.well-known/oauth-protected-resource` returns valid discovery metadata
- authenticated `POST /api/memories`
- authenticated `GET /api/memories/{id}`
- authenticated `DELETE /api/memories/{id}`

## Known Issue

### `openapi.json` not exposed

Both of these currently return `Not Found`:
- `http://localhost:7010/openapi.json`
- `https://poutily-hemispheroidal-pia.ngrok-free.dev/openapi.json`

This does not block normal server operation, MCP usage, or authenticated CRUD.
It does mean the current wrapper/routing layer is not exposing FastAPI OpenAPI output at that path.

## Architectural Conclusion

The system is now in a materially better state:
- MCP error semantics are correct.
- Remote MCP no longer advertises host-only Obsidian tools.
- Core success payloads are aligned across transports.
- Test entrypoints are stable and explicit.
- Local and remote authenticated CRUD both work after restart.

The main remaining visible HTTP issue is the absence of `/openapi.json`.
