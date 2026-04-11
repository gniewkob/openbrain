# Operating Manual: OpenBrain Unified (v2.3)

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
3. **Root Redirect (307)**: Root path `/` requests are automatically redirected to the configured streamable transport path (default: `/sse`, override: `MCP_STREAMABLE_HTTP_PATH`). The 307 status code ensures that the `POST` method and JSON-RPC payload are preserved. `MCP_STREAMABLE_HTTP_PATH` must start with `/`, cannot be exactly `/`, cannot exceed 128 chars, and cannot include query/fragment/spaces/backslashes/double-slashes or `.`/`..` segments (guardrails against redirect/routing drift).
4. **Internal Auth**: MCP communicates with the internal REST API using the `X-Internal-Key` header, bypassing OIDC/Auth0 for system processes. The comparison uses `hmac.compare_digest` to prevent timing-based key guessing. In `PUBLIC_MODE=true`, this key must be explicitly configured and must not use the dev default.
5. **Health Probe Timeout**: transport readiness fallback probes use `MCP_HEALTH_PROBE_TIMEOUT_S` (default `5.0`) for `/readyz`, `/api/v1/readyz`, `/healthz`, and `/api/v1/health`. Allowed range: finite `(0, 30]`, and it must not exceed `BACKEND_TIMEOUT_S` in both unified transport and stdio gateway startup.
6. **Backend Timeout Validation**: MCP backend timeout (`BACKEND_TIMEOUT_S`) must stay in finite `(0, 120]`; invalid values fail fast at config load in both unified transport and stdio gateway startup.
7. **Backend URL Validation**: MCP backend URL (`BRAIN_URL`) must be a valid `http(s)` URL and must not include credentials/path/query/fragment or internal whitespace, to avoid silent runtime misrouting. Surrounding whitespace and trailing `/` are normalized away in both unified transport and stdio gateway startup paths.

## Security Hardening (v2.3)
The following security improvements were applied:
- **Timing-safe key comparison**: `X-Internal-Key` is now compared with `hmac.compare_digest`, eliminating early-exit timing attacks.
- **Thread-safe policy registry**: `POLICY_REGISTRY` is updated via atomic reference replacement under a lock; reads also hold the lock snapshot. Eliminates the race window between `clear()` and `update()`.
- **MCP source tagging**: `brain_store` tags records with `MCP_SOURCE_SYSTEM` (env var, default `other`; `SOURCE_SYSTEM` is accepted as a compatibility alias for startup config). Value is normalized (`trim + lowercase`) and must match `[a-z0-9][a-z0-9_-]{0,31}` (for example: `claude`, `codex`, `chatgpt`) to keep provenance metadata consistent. When both are present, `MCP_SOURCE_SYSTEM` takes precedence.
- **Per-record authorization for `export` and `sync-check`**: both flows now reuse record-level access gates; unauthorized lookups are masked as `404` for `sync-check`.
- **Local Obsidian opt-in**: `brain_obsidian_*` tools in the local stdio gateway require `ENABLE_LOCAL_OBSIDIAN_TOOLS=1` and are no longer exposed by default.
- **HTTP transport Obsidian opt-in**: streamable HTTP transport exposes `brain_obsidian_*` only when `ENABLE_HTTP_OBSIDIAN_TOOLS=1` at process start.
- **HTTP gateway startup validation**: `mcp_http` now fail-fast validates `PUBLIC_BASE_URL` (URL shape + HTTPS outside localhost) and `MCP_HTTP_PORT` range before serving OAuth endpoints.
- **Default-local ingress posture**: `ngrok` lives in the Compose `public` profile and starts only with `ENABLE_NGROK=1`.
- **Request bounds**: canonical and legacy schemas now cap `top_k`, `limit`, `max_items`, bulk sizes, export IDs, and key string lengths to reduce accidental expensive requests.
- **Access denial telemetry**: Prometheus counters now expose `access_denied_total` and reason-specific breakdowns for `admin`, `domain`, `owner`, and `tenant`.
- **Metadata-aware idempotent writes**: writes are no longer silently skipped when only metadata changes and `content_hash` stays the same.
- **Telemetry durability**: counters and histograms are now restored across restarts via PostgreSQL-backed persistence.
- **Shared telemetry counters**: `TELEMETRY_BACKEND=redis` enables cross-worker counter aggregation using Redis (`TELEMETRY_REDIS_URL` or `REDIS_URL`), with automatic fallback to in-memory counters when Redis is unavailable.
- **Metrics exception accounting**: unhandled request failures are counted as `500` and still contribute to request-duration histograms.
- **MCP log redaction**: transport logging now redacts `content`, `title`, `tenant_id`, `match_key`, `obsidian_ref`, and `custom_fields`.
- **Lazy OIDC refresh lock**: the OIDC verifier avoids import-time event-loop binding by creating the async lock lazily.
- **Request tracing cleanup**: `RequestIDMiddleware` now clears `structlog` context even when a request raises before response creation.
- **Guardrail CI refresh**: the smoke workflow now installs `unified`, runs public-mode startup security tests directly, and no longer carries the removed `OPENBRAIN_DISABLE_DB_CONFIG_VALIDATION` flag.
- **Gateway/HTTP parity**: stdio gateway records now carry the same V1 provenance fields (`title`, `summary`, `source`, `governance`) needed for parity with the HTTP MCP transport.
- **Secret scanner expansion**: committed-secret checks now cover tracked text files more broadly, including `.env.example`, generic `*_TOKEN` / `*_SECRET` patterns, bearer headers, and URL-embedded credentials in config-like files.
- **Telemetry shutdown hygiene**: the periodic telemetry sync task is now cancelled and awaited cleanly during FastAPI lifespan shutdown.

## Tools and Hierarchy (Tiers)
The system guides AI behavior by categorizing tools:
- **Tier 1 (Core)**: `search`, `get`, `store`, `update` — Safe for daily use.
- **Tier 2 (Advanced)**: `list`, `get_context`, `delete`, `export`, `sync_check`, `obsidian_vaults`, `obsidian_read_note`, `obsidian_sync` — Require explicit user intent.
- **Tier 3 (Admin)**: `store_bulk`, `upsert_bulk`, `maintain` — Batch and system-wide operations.

Capabilities payload note:
- `brain_capabilities` now includes a transport-agnostic `obsidian` object (`mode`, `status`, `tools`, `reason`).
- `brain_capabilities` now includes `health.overall` plus `health.components` (`api`, `db`, `vector_store`, `obsidian`) for component-level truthfulness.
- `brain_capabilities` metadata contract is strict: `api_version` must follow `MAJOR.MINOR.PATCH` and must be present as a key in `schema_changelog`.
- capabilities manifest contract is strict: each tool tier list must contain non-empty string names only and must not contain duplicates (no silent fallback defaults).
- request/runtime contracts are strict too: `request_contracts.json` and `runtime_limits.json` must be valid and complete (no silent fallback to baked-in defaults).
- this strict contract loading is enforced in both transports (HTTP + stdio gateway), so drift is caught early at startup/tests.
- request contract string fields are canonicalized (`trim`) at load time to keep audit placeholders deterministic (`updated_by_default`).
- MCP tool flag `include_test_data` is strict boolean input on `brain_list` / `brain_search`; non-boolean values are rejected (no silent coercion).
- V1 backend `/api/v1/memory/find` also enforces strict boolean typing for `filters.include_test_data`; invalid types return HTTP 422 (no silent truthy/falsy coercion).
- Admin diagnostics endpoint `/api/v1/memory/admin/test-data/report` provides a read-only hygiene snapshot (hidden test-data counts, status/domain breakdown, sanitized sample IDs/owners/match_keys) to support controlled cleanup decisions.
- Admin execution endpoint `/api/v1/memory/admin/test-data/cleanup-build` provides controlled cleanup for `build` test-data with explicit `dry_run` default and bounded `limit`.
- response normalizers canonicalize actor fields (`created_by`, `updated_by`) in transport output for legacy-hit resilience.
- Legacy transport-specific keys (`obsidian_http`, `obsidian_local`) remain for backward compatibility.

## Governance Rules
- `corporate` is append-only by policy. Treat `update` as version creation, not overwrite.
- `build` and `personal` are mutable by default. Use append-only only when historical state matters.
- `store_bulk` is for net-new ingestion. `upsert_bulk` is for deterministic pipelines with stable `match_key`.
- Run `maintain` with `dry_run=true` first. Treat non-dry-run maintenance as a controlled operation.
- `search` and `get_context` should represent active truth, not superseded history.
- For `PATCH /api/v1/memory/{id}`, authenticated subject is authoritative audit actor.
  Request-level `updated_by` is accepted for compatibility but overridden at API boundary.
- Gateway and streamable transport send a canonical `updated_by="agent"` placeholder
  to avoid spoofed-client actor semantics in request payloads.
- Read-model normalization trims actor fields for deterministic audit display on legacy records:
  `created_by` is normalized (`trim`, fallback `"agent"`), and `updated_by` is normalized from metadata with fallback to normalized `created_by`.

## V1 API Reference (Canonical Endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/memory/write` | Single write (all domains + write modes) |
| `POST` | `/api/v1/memory/write-many` | Batch write |
| `GET`  | `/api/v1/memory/{id}` | Retrieve by ID — returns canonical `MemoryRecord` shape |
| `POST` | `/api/v1/memory/find` | Hybrid vector + metadata search |
| `POST` | `/api/v1/memory/get-context` | Synthesize grounding pack for LLM context |

Use V1 endpoints for new integrations. Legacy `/api/memories/*` paths remain for backward compatibility.

## Domain Write Semantics (v2.3 update)

`brain_store(domain="corporate")` now works correctly via both MCP gateway and direct V1 calls.
The write engine automatically upgrades `upsert` mode to `append_version` for the corporate domain.
Idempotency (skip if content unchanged) applies to all modes including `append_version`,
preventing phantom version creation on repeated identical writes.
The idempotency check now includes metadata state as well, so metadata-only updates are persisted correctly.

## Test Posture

- `unified/tests` now passes full `unittest discover` as a supported regression path.
- Transport parity tests remain part of CI, but they are skipped during bare `unified` discovery when gateway-only dependencies are not installed.
- Route registration, middleware, lifespan, and app-factory modules now have direct tests instead of relying only on indirect coverage through `main.py`.
- `main.py` and `crud.py` remain intentionally covered only where they still represent public assembly or compatibility surfaces.
- Controlled Obsidian E2E harness (opt-in only):
  - test file: `unified/tests/integration/test_obsidian_controlled_e2e.py`
  - run with: `RUN_CONTROLLED_OBSIDIAN_E2E=1 OPENBRAIN_BASE_URL=http://127.0.0.1:7010 pytest -q unified/tests/integration/test_obsidian_controlled_e2e.py`
  - optional assertion: set `OBSIDIAN_TEST_VAULT=<vault-name>`

## CI Release Gate (Branch Protection)

Baseline branch in this repository is `master` (`gh repo view`).
As of 2026-04-08 the branch is protected (verified via `gh api repos/gniewkob/openbrain/branches/master/protection`).

Recommended required checks:
- `lint`
- `test`
- `security`
- `contract-integrity`
- `guardrails`
- `smoke`
- `gateway-smoke`
- `transport-parity`
- `GitGuardian Security Checks`

Operator verification commands:
```bash
gh workflow list
gh run list --limit 20 --json workflowName,displayTitle,status,conclusion,headBranch,event,url
gh run view <RUN_ID> --json jobs
python scripts/check_release_gate.py                         # audit-only
RELEASE_GATE_ENFORCE=1 python scripts/check_release_gate.py # fail on policy drift
```

CI guardrail:
- `Unified Smoke Tests / guardrails` enforces release-gate policy via `scripts/check_release_gate.py` with `RELEASE_GATE_ENFORCE=1`.
- `Unified Smoke Tests / guardrails` also enforces repository hygiene via `scripts/check_repo_hygiene.py` (known debug artifacts deny-list).
- `Unified Smoke Tests / guardrails` enforces compose safety via `scripts/check_compose_guardrails.py` (no hardcoded DB defaults + required public MCP transport snippets such as `http://mcp-http:7011` and `--url=${NGROK_DOMAIN}`).
- `Unified Smoke Tests / guardrails` enforces capabilities manifest parity via `scripts/check_capabilities_manifest_parity.py` (HTTP transport and stdio gateway loaders must stay contract-equivalent).
- `Unified Smoke Tests / guardrails` enforces capabilities metadata parity via `scripts/check_capabilities_metadata_parity.py` (`api_version`/changelog loader semantics must stay contract-equivalent across transports).
- `Unified Smoke Tests / guardrails` enforces capabilities health parity via `scripts/check_capabilities_health_parity.py` (`build_capabilities_health` and component mapping logic must stay contract-equivalent across transports).
- `Unified Smoke Tests / guardrails` enforces capabilities tier status parity via `scripts/check_capabilities_tier_status_parity.py` (`brain_capabilities` must keep aligned tier status values in stdio and HTTP and stay inside contract `tier_status_values`).
- `Unified Smoke Tests / guardrails` enforces backend probe contract parity via `scripts/check_backend_probe_contract_parity.py` (`_get_backend_status` must keep aligned probe order `/readyz` -> `/api/v1/readyz` plus fallback probes `/healthz` and `/api/v1/health`, with stable probe labels/reason fragments).
- `Unified Smoke Tests / guardrails` enforces request/runtime contract parity via `scripts/check_request_runtime_parity.py` (`request_contracts` and `runtime_limits` loader/validator semantics must stay contract-equivalent across transports).
- `Unified Smoke Tests / guardrails` enforces shared backend HTTP client reuse via `scripts/check_shared_http_client_reuse.py` (both transports must keep module-level shared `httpx.AsyncClient` pooling semantics).
- `Unified Smoke Tests / guardrails` enforces selected MCP tool signature parity via `scripts/check_tool_signature_parity.py` (`brain_search`, `brain_list`, `brain_delete`, `brain_update` argument contract must stay transport-equivalent).
- `Unified Smoke Tests / guardrails` enforces admin parameter bounds parity via `scripts/check_admin_bounds_parity.py` (`brain_test_data_report.sample_limit` and `brain_cleanup_build_test_data.limit` ranges/defaults must stay transport-equivalent).
- `Unified Smoke Tests / guardrails` enforces admin endpoint contract parity via `scripts/check_admin_endpoint_contract_parity.py` (`brain_test_data_report` and `brain_cleanup_build_test_data` must keep aligned method/path-alias/payload-key mapping across stdio and HTTP transports).
- `Unified Smoke Tests / guardrails` enforces MCP tool inventory parity via `scripts/check_tool_inventory_parity.py` (all non-Obsidian tools must match across canonical/compatibility transports; compatibility transport keeps only the approved Obsidian subset).
- `Unified Smoke Tests / guardrails` enforces capabilities tools truthfulness via `scripts/check_capabilities_tools_truthfulness.py` (manifest-declared tools must map to real `@mcp.tool` functions in both transports).
- `Unified Smoke Tests / guardrails` enforces `brain_search` filter parity via `scripts/check_search_filter_parity.py` (`owner` and `include_test_data` wiring to backend filters must stay transport-equivalent).
- `Unified Smoke Tests / guardrails` enforces `brain_list` filter parity via `scripts/check_list_filter_parity.py` (`status`, `owner`, `tenant_id`, `include_test_data` wiring to backend filters must stay transport-equivalent).
- `Unified Smoke Tests / guardrails` enforces response normalizers parity via `scripts/check_response_normalizers_parity.py` (actor normalization and legacy hit-shape normalization must stay contract-equivalent across transports).
- `Unified Smoke Tests / guardrails` enforces HTTP error adapter parity via `scripts/check_http_error_adapter_parity.py` (shared status labels + detail-hint mapping + production-safe request-failure fallback must stay transport-equivalent).
- `Unified Smoke Tests / guardrails` enforces HTTP error contract semantics via `scripts/check_http_error_contract_semantics.py` (`http_error_contracts.json` must retain required status labels, fallback labels, and `missing_session_id` hint semantics).
- `Unified Smoke Tests / guardrails` enforces capabilities status truthfulness via `scripts/check_capabilities_truthfulness.py` (health contract + fallback probe invariants).
  - contract now pins tier status semantics via `tier_status_values` (`stable`, `active`, `guarded`) to prevent capability-level drift.
- `Unified Smoke Tests / guardrails` enforces audit semantics via `scripts/check_audit_semantics.py` (`created_by/updated_by` invariants at schema/API/write boundaries).
- `Unified Smoke Tests / guardrails` enforces cleanup actor semantics via `scripts/check_cleanup_actor_semantics.py` (`cleanup_build_test_data` must preserve `actor = get_subject(_user) or "agent"` and forward `actor` to use-case layer for auditable deletes).
- `Unified Smoke Tests / guardrails` enforces update actor semantics parity via `scripts/check_update_audit_semantics_parity.py` (`brain_update` must normalize compatibility `updated_by` input and persist canonical server-side audit actor).
- `Unified Smoke Tests / guardrails` enforces `brain_delete` error parity via `scripts/check_delete_semantics_parity.py` (403/404 mappings must stay aligned between stdio gateway and HTTP transport).
- `Unified Smoke Tests / guardrails` enforces export redaction contract semantics via `scripts/check_export_contract.py` (`EXPORT_POLICY` coverage + restricted fallback + required redactions).
- `Unified Smoke Tests / guardrails` enforces Obsidian gating/contract semantics via `scripts/check_obsidian_contract.py` (feature-flag + capabilities + manifest subset checks).
- `Unified Smoke Tests / guardrails` enforces telemetry/monitoring contract parity via `scripts/check_telemetry_contract_parity.py` (all gauge metrics emitted by `telemetry_gauges` must be listed in the monitoring metrics contract).
- `Unified Smoke Tests / guardrails` enforces dashboard memory panel semantics via `scripts/check_dashboard_memory_semantics.py` (visible/all/hidden memory panels and hidden-share panel must keep canonical PromQL expressions).
- `Unified Smoke Tests / guardrails` enforces hidden test-data alert parity via `scripts/check_hidden_test_data_alert_parity.py` (runtime alert rules and docs alert rules must keep aligned alert names and threshold semantics).
- `Unified Smoke Tests / guardrails` enforces monitoring contract via `scripts/validate_monitoring_contract.py` (dashboard + alert-rule metric references must remain inside the declared contract).
- `Unified Smoke Tests / guardrails` executes the consolidated static bundle via `scripts/check_local_guardrails.py` (hygiene + compose safety + capabilities truthfulness + audit semantics + Obsidian contract + monitoring contract).
- `check_local_guardrails.py` enforces per-step timeouts (default 60s, monitoring contract 90s) and fails with exit code `124` on timeout.
- `Unified Smoke Tests / guardrails` runs lightweight pytest coverage for guardrail runners:
  - `unified/tests/test_local_guardrails_runner.py`
  - `unified/tests/test_pr_readiness_runner.py`
  - `unified/tests/test_repo_hygiene_guardrail.py`
  - `unified/tests/test_compose_guardrails.py`
  - `unified/tests/test_secret_scan_guardrail.py`
  - `unified/tests/test_capabilities_manifest_parity_guardrail.py`
  - `unified/tests/test_capabilities_metadata_parity_guardrail.py`
  - `unified/tests/test_capabilities_health_parity_guardrail.py`
  - `unified/tests/test_capabilities_tier_status_parity_guardrail.py`
  - `unified/tests/test_backend_probe_contract_parity_guardrail.py`
  - `unified/tests/test_request_runtime_parity_guardrail.py`
  - `unified/tests/test_shared_http_client_reuse_guardrail.py`
  - `unified/tests/test_tool_signature_parity_guardrail.py`
  - `unified/tests/test_admin_bounds_parity_guardrail.py`
  - `unified/tests/test_admin_endpoint_contract_parity_guardrail.py`
  - `unified/tests/test_tool_inventory_parity_guardrail.py`
  - `unified/tests/test_capabilities_tools_truthfulness_guardrail.py`
  - `unified/tests/test_response_normalizers_parity_guardrail.py`
  - `unified/tests/test_http_error_adapter_parity_guardrail.py`
  - `unified/tests/test_http_error_contract_semantics_guardrail.py`
  - `unified/tests/test_capabilities_truthfulness_guardrail.py`
  - `unified/tests/test_audit_semantics_guardrail.py`
  - `unified/tests/test_cleanup_actor_semantics_guardrail.py`
  - `unified/tests/test_update_audit_semantics_parity_guardrail.py`
  - `unified/tests/test_export_contract_guardrail.py`
  - `unified/tests/test_obsidian_contract_guardrail.py`
  - `unified/tests/test_monitoring_contract_guardrail.py`
  - `unified/tests/test_telemetry_contract_parity_guardrail.py`
  - `unified/tests/test_dashboard_memory_semantics_guardrail.py`
  - `unified/tests/test_hidden_test_data_alert_parity_guardrail.py`
  - `unified/mcp-gateway/tests/test_shared_client_reuse.py`

Local PR readiness:
- `python3 scripts/check_pr_readiness.py`
- or `make pr-readiness`
- local static guardrails only: `make local-guardrails`
- guardrail runner pytest bundle only: `make guardrail-tests`
- contract integrity smoke pytest bundle only: `make contract-smoke`
- step-level timeouts are enforced (`local guardrails`: 180s, test steps: 300s) to prevent indefinite hangs.
- bundle includes:
  - `check_local_guardrails.py`
  - guardrail runner unit tests
  - contract integrity smoke (`test_contract_integrity.py`, `test_capabilities_response_contract.py`, `test_health_route_alias_contract.py`, `test_admin_openapi_contract.py`, `test_transport_parity.py`)

Local monitoring contract check:
- `make monitoring-check`
- optional live-mode validation: `python3 scripts/validate_monitoring_contract.py --check-live --metrics-url http://127.0.0.1:9180/metrics`
- default mode forbids `vector(0)` in monitoring PromQL expressions (dashboards and alert rules; opt-out for migration only: `--allow-vector-zero`)
- `active_memories_all_total` now exposes all active rows including hidden test fixtures (`active_memories_total + hidden_test_data_active_total`) for dashboard truthfulness.
- Grafana memory diagnostics now include `Active Memories (Visible Excl Test Data)`, `Active Memories (All incl Test Data)`, `Hidden Test Data (Active Only)`, and `Hidden Test Data Share (Active)`.

Branch protection policy (recommended):
- Require pull request before merging.
- Require status checks above to pass before merging.
- Require branches to be up to date before merging.
- Dismiss stale pull request approvals when new commits are pushed.
- Include administrators (no bypass in normal mode).

Backup branch inventory note (2026-04-08):
- Local `backup/local-pre-sync-20260401-232135` has no unique commits relative to `master` and can be removed safely when no longer needed.
- Remote `origin/backup/local-pre-sync-20260401-232135` still contains unique historical commits (ahead of `origin/master`), so deletion should be treated as a deliberate archive decision (tag/patch export first, then delete).

## Export Policy
- **Admin callers** (privileged users authenticated via JWT) receive fully unredacted records.
- **Service account callers** (`X-Internal-Key` subject = `internal`) also receive full records since they have already passed `_require_admin()`.
- Format: pass `"format": "jsonl"` in the request body to receive newline-delimited JSON (`application/x-ndjson`) instead of a JSON array.
- `export` now validates every requested record against the same record-level access rules as `read_memory`; a privileged caller still needs matching domain/tenant/owner scope where applicable.

## Known Limitations
- `tenant_id` is now available as a first-class indexed column and remains mirrored in `metadata_` only for compatibility with older records and tools. New code should treat the column as the source of truth.
- Telemetry gauges and histograms remain process-local. Counter metrics can now be shared across workers by setting `TELEMETRY_BACKEND=redis`.
- MCP transport and stdio gateway now reuse shared backend `httpx.AsyncClient` instances to preserve connection pooling under sustained tool traffic.
- stdio gateway now refreshes shared backend `httpx.AsyncClient` automatically when runtime backend config drifts (`BRAIN_URL` / timeout / internal key), mirroring HTTP transport behavior.
- The metrics bridge still uses Python's basic `HTTPServer`, which is sufficient for the current single-scrape local topology but not intended as a hardened multi-client ingress component.

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
- **`./start_unified.sh stop` leaves `openbrain_net_unified` behind**: This used to happen when the stack had been started with `ENABLE_NGROK=1`, but `stop` was later run without that env flag, leaving `openbrain-unified-ngrok` attached to the network. The stop path now tears down both the base stack and the Compose `public` profile, so `ngrok` and `openbrain_net_unified` are removed correctly.
- **Python `httpx`/`urllib` probes fail while `curl` to `localhost` works**: In the Codex CLI sandbox, Python socket connections to `127.0.0.1` can be blocked with `[Errno 1] Operation not permitted`. This is a sandbox restriction, not an OpenBrain or MCP bug. Validate local MCP connectivity with `curl`, or run the Python probe outside the sandbox when you need to exercise the HTTP client code path.
- **Ollama Issues**: If search returns errors, verify that the model is loaded: `docker exec openbrain-unified-ollama ollama list`.
- **Swagger UI not loading**: Access `/docs` directly via the REST port (`http://localhost:7010/docs`). The combined ASGI wrapper now correctly routes `/docs` to FastAPI.
- **corporate domain writes returning "failed"**: This was a bug in v2.1. Upgrade to v2.2. The write engine now auto-upgrades `upsert` mode to `append_version` for corporate domain.
