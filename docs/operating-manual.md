# Operating Manual: OpenBrain Unified (v2.1)

## Architecture Overview
The system runs on Docker Compose. The primary entry point is `src.combined:app`, which acts as an intelligent ASGI wrapper.

### Core Services:
- `db`: PostgreSQL with `pgvector` extension.
- `unified-server`: Hybrid server (FastAPI for REST + Starlette for MCP).
- `embedding-service`: Local Ollama instance (`nomic-embed-text`).
- `ngrok`: Secure tunnel for external access (starts by default).

### Quick Start
```bash
./start_unified.sh start
```

## MCP Transport Mechanism
Version 2.1 introduces the "Industrial Wrapper" in `combined.py`, designed for maximum connection stability with ChatGPT:
1. **OAuth Discovery**: Requests to `/.well-known/...` are intercepted and handled directly by the wrapper, eliminating configuration errors in ChatGPT.
2. **Root Redirect (307)**: Root path `/` requests are automatically redirected to `/sse`. The 307 status code ensures that the `POST` method and JSON-RPC payload are preserved.
3. **Internal Auth**: MCP communicates with the internal REST API using the `X-Internal-Key` header, bypassing OIDC/Auth0 for system processes.

## Tools and Hierarchy (Tiers)
The system guides AI behavior by categorizing tools:
- **Tier 1 (Core)**: `search`, `get`, `store`, `update` — Safe for daily use.
- **Tier 2 (Advanced)**: `list`, `get_context`, `delete`, `export`, `sync_check` — Require explicit user intent.
- **Tier 3 (Admin)**: `store_bulk`, `upsert_bulk`, `maintain` — Batch and system-wide operations.

## Troubleshooting
- **404 Not Found in ChatGPT**: Ensure you are using the base ngrok URL without any suffix. The server handles all routing.
- **401 Unauthorized**: Check if `INTERNAL_API_KEY` in your `.env` file matches the one in the server configuration.
- **Ollama Issues**: If search returns errors, verify that the model is loaded: `docker exec openbrain-unified-ollama ollama list`.
