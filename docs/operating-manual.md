# Operating Manual: OpenBrain Unified (v2.2)

## Architecture Overview
The system runs on Docker Compose. The primary entry point is `src.combined:app`, which acts as an intelligent ASGI wrapper.

### Core Services:
- `db`: PostgreSQL with `pgvector` extension.
- `unified-server`: Hybrid server (FastAPI for REST + Starlette for MCP).
- `embedding-service`: Local Ollama instance (`nomic-embed-text`).
- `ngrok`: Secure tunnel for external access (optional Compose `public` profile, disabled by default).

### Quick Start
```bash
./start_unified.sh start
ENABLE_NGROK=1 ./start_unified.sh start   # enable external ngrok tunnel
```

## MCP Transport Mechanism
The "Industrial Wrapper" in `combined.py` provides stable ASGI routing:
1. **OAuth Discovery**: Requests to `/.well-known/...` are forwarded to the FastAPI REST app (single authoritative handler in `main.py`). No duplicate handlers.
2. **API + Docs**: `/api/*`, `/docs`, `/openapi.json`, `/redoc`, and health endpoints all route to FastAPI.
3. **Root Redirect (307)**: Root path `/` requests are automatically redirected to `/sse`. The 307 status code ensures that the `POST` method and JSON-RPC payload are preserved.
4. **Internal Auth**: MCP communicates with the internal REST API using the `X-Internal-Key` header, bypassing OIDC/Auth0 for system processes. The comparison uses `hmac.compare_digest` to prevent timing-based key guessing. In `PUBLIC_MODE=true`, this key must be explicitly configured and must not use the dev default.

## Security Hardening (v2.2)
The following security improvements were applied:
- **Timing-safe key comparison**: `X-Internal-Key` is now compared with `hmac.compare_digest`, eliminating early-exit timing attacks.
- **Thread-safe policy registry**: `POLICY_REGISTRY` is updated via atomic reference replacement under a lock; reads also hold the lock snapshot. Eliminates the race window between `clear()` and `update()`.
- **MCP source tagging**: `brain_store` tags records with `MCP_SOURCE_SYSTEM` (env var, default `other`). Override in your env to identify the calling agent (e.g., `claude`, `codex`, `chatgpt`).

## Tools and Hierarchy (Tiers)
The system guides AI behavior by categorizing tools:
- **Tier 1 (Core)**: `search`, `get`, `store`, `update` — Safe for daily use.
- **Tier 2 (Advanced)**: `list`, `get_context`, `delete`, `export`, `sync_check`, `obsidian_vaults`, `obsidian_read_note`, `obsidian_sync` — Require explicit user intent.
- **Tier 3 (Admin)**: `store_bulk`, `upsert_bulk`, `maintain` — Batch and system-wide operations.

## Governance Rules
- `corporate` is append-only by policy. Treat `update` as version creation, not overwrite.
- `build` and `personal` are mutable by default. Use append-only only when historical state matters.
- `store_bulk` is for net-new ingestion. `upsert_bulk` is for deterministic pipelines with stable `match_key`.
- Run `maintain` with `dry_run=true` first. Treat non-dry-run maintenance as a controlled operation.
- `search` and `get_context` should represent active truth, not superseded history.

## V1 API Reference (Canonical Endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/memory/write` | Single write (all domains + write modes) |
| `POST` | `/api/v1/memory/write-many` | Batch write |
| `GET`  | `/api/v1/memory/{id}` | Retrieve by ID — returns canonical `MemoryRecord` shape |
| `POST` | `/api/v1/memory/find` | Hybrid vector + metadata search |
| `POST` | `/api/v1/memory/get-context` | Synthesize grounding pack for LLM context |

Use V1 endpoints for new integrations. Legacy `/api/memories/*` paths remain for backward compatibility.

## Domain Write Semantics (v2.2 update)

`brain_store(domain="corporate")` now works correctly via both MCP gateway and direct V1 calls.
The write engine automatically upgrades `upsert` mode to `append_version` for the corporate domain.
Idempotency (skip if content unchanged) applies to all modes including `append_version`,
preventing phantom version creation on repeated identical writes.

## Export Policy
- **Admin callers** (privileged users authenticated via JWT) receive fully unredacted records.
- **Service account callers** (`X-Internal-Key` subject = `internal`) also receive full records since they have already passed `_require_admin()`.
- Format: pass `"format": "jsonl"` in the request body to receive newline-delimited JSON (`application/x-ndjson`) instead of a JSON array.

## Known Limitations
- `tenant_id` is currently stored in `metadata_` rather than a dedicated indexed column. This is an accepted interim design, but if tenancy becomes a hard operational boundary the field should move into the relational model with an index.
- In-memory telemetry (`TelemetryRegistry`) is per-process. Multi-worker uvicorn deployments will report inconsistent metrics per scrape. Use `WEB_CONCURRENCY=1` (default in the Docker stack) or replace with a shared counter backend (Redis, etc.) if multi-worker is needed.

## Operational Thresholds
- `policy_skip_per_maintain_run_ratio`: `watch >= 0.25`, `elevated >= 1.0`
- `duplicate_candidates_per_maintain_run_ratio`: `watch >= 1.0`, `elevated >= 5.0`
- `search_zero_hit_ratio`: `watch >= 0.05`, `elevated >= 0.15`
- `/api/diagnostics/metrics` returns `summary.health` and `summary.health_status`
- `/metrics` exposes `operational_health_status` and `*_watch_threshold` / `*_elevated_threshold` gauges for scrape-based alerting
- use `/healthz` and `/readyz` for probes; `/health` and `/metrics` require authentication in public mode
- example Prometheus rules are provided in [prometheus-alerts.yml](prometheus-alerts.yml)

For the full production operating model, see [Governance Layer](governance-layer.md).

## Troubleshooting
- **404 Not Found in ChatGPT**: Ensure you are using the base ngrok URL without any suffix. The server handles all routing.
- **401 Unauthorized**: Check OIDC config in public mode, or verify that `INTERNAL_API_KEY` in your `.env` file matches the server configuration for trusted internal callers.
- **Ollama Issues**: If search returns errors, verify that the model is loaded: `docker exec openbrain-unified-ollama ollama list`.
- **Swagger UI not loading**: Access `/docs` directly via the REST port (`http://localhost:7010/docs`). The combined ASGI wrapper now correctly routes `/docs` to FastAPI.
- **corporate domain writes returning "failed"**: This was a bug in v2.1. Upgrade to v2.2. The write engine now auto-upgrades `upsert` mode to `append_version` for corporate domain.
