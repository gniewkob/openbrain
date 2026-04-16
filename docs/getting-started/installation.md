# OpenBrain — Installation and Configuration Guide

> Version: (Industrial)

---

## Architecture

```
Local Clients (Claude Desktop) ──┐
                                 ├─→ unified-server (:7010) ─→ PostgreSQL + pgvector
Remote Clients (ChatGPT) ────────┤          ↑ (SSE / JSON-RPC)        ↑
                                 └─→ ngrok ─┘                  Ollama (embed)
```

- **Backend**: FastAPI + FastMCP in Docker (port 7010, bound to `127.0.0.1` in the local compose stack).
- **Industrial Wrapper**: Stable ASGI routing handling MCP and OAuth Discovery automatically.
- **Domains**: `corporate` (append-only), `build` (projects), `personal` (private).

---

## 1. Docker Compose — struktura plików

| Plik | Projekt Docker | Cel | Kiedy uruchamiać |
|---|---|---|---|
| `docker-compose.unified.yml` | `openbrain` | Produkcja — DB, Redis, API, MCP gateway, ngrok | Zawsze; `./start_unified.sh start` |
| `docker-compose.mcp-dev.yml` | `openbrain-dev` | Narzędzia deweloperskie — context7, playwright, markitdown, firecrawl, desktop-commander | Tylko podczas sesji deweloperskiej |
| `docker-compose.monitoring.yml` | osobny | Prometheus + Grafana | Opcjonalnie, do monitoringu |

Każdy plik compose ma unikalną nazwę projektu (`name:` w YAML). Dzięki temu kontenery z `mcp-dev` nie pojawiają się jako sieroty podczas startu produkcyjnego stacku.

> Szczegóły sesji deweloperskiej: [operations/dev-session.md](../operations/dev-session.md)

---

## 2. Startup

```bash
cd ~/Repos/openbrain
./start_unified.sh start     # Starts local-only services: DB + Ollama + Server + Monitoring
ENABLE_NGROK=1 ./start_unified.sh start   # Also enables the public ngrok profile
./start_unified.sh status    # Check status and view current URLs
```

**Note:** ngrok is now **disabled by default**. Enable it only for explicit public/remote use with `ENABLE_NGROK=1`. The public URL for ChatGPT changes on every restart unless you use a static ngrok domain.

### Monitoring Endpoints

- OpenBrain API: `http://localhost:7010`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` by default, or `http://localhost:$GRAFANA_PORT`
- Unauthenticated liveness probe: `http://localhost:7010/healthz`
- Readiness probe: `http://localhost:7010/readyz`
- Auth-gated health summary for operators: `http://localhost:7010/health`
- Default Grafana login: `admin / admin` unless overridden with `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`
- Default Grafana credentials are dev-only. Replace them in any shared or public deployment.
- When `PUBLIC_MODE=true` or `PUBLIC_BASE_URL` is set, `./start_unified.sh start` now refuses to start with default PostgreSQL or Grafana credentials.

---

## 3. MCP Tools (15 + 1 Diagnostic)

The system uses intent-based descriptions ("Use when / Do not use when") to guide AI models.

### Tier 0: Diagnostics
- `brain_capabilities`: Check runtime status and tool availability. **Run this first in a new session.**

### Tier 1: Core (Daily Work)
- `brain_search`: Semantic search (primary tool).
- `brain_get`: Retrieve a specific record by ID. Returns canonical V1 `MemoryRecord` shape (includes `title`, `summary`, `source`, `governance` fields).
- `brain_store`: Save a single note/decision. Works for all three domains including `corporate` (auto-versioned).
- `brain_update`: Update an existing record. Corporate records create a new version automatically.

### Tier 2: Advanced (Specialized)
- `brain_list`: Browse the database with filters (domain, owner).
- `brain_get_context`: Build a synthetic context pack from multiple records.
- `brain_delete`: Delete (allowed ONLY for `build` and `personal` domains).
- `brain_export`: Export data to JSON or JSONL. Admin callers receive fully unredacted records.
- `brain_sync_check`: Verify consistency with Obsidian (hash check). Requires exactly one of `memory_id`, `match_key`, or `obsidian_ref`.
- `brain_obsidian_vaults`: List local Obsidian vaults visible to the backend.
- `brain_obsidian_read_note`: Read a note with parsed frontmatter, tags, and content hash.
- `brain_obsidian_sync`: One-way sync from Obsidian into OpenBrain using deterministic match keys.

### Tier 3: Admin (High Risk)
- `brain_store_bulk`: Batch save (up to 50 records).
- `brain_upsert_bulk`: Intelligent synchronization (`match_key` based).
- `brain_maintain`: System maintenance (deduplication, link fixing).

---

## 4. Client Configuration

### Codex CLI / Gemini CLI (Local)
Use a local `stdio` server for maximum performance and reliable authentication. In project `.mcp.json`, `~/.codex/config.toml`, or `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "openbrain": {
      "type": "stdio",
      "command": "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway/.venv/bin/python",
      "args": ["-m", "src.main"],
      "cwd": "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway",
      "env": {
        "BRAIN_URL": "http://127.0.0.1:7010",
        "INTERNAL_API_KEY": "set-a-unique-local-key-if-public-mode-is-enabled",
        "ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"
      }
    }
  }
}
```

### Claude Desktop (Local)
If `PUBLIC_MODE=true` is active, Claude Desktop must also provide the `INTERNAL_API_KEY`. Since the standard SSE config doesn't support custom headers, **stdio** is the recommended configuration for Claude Desktop as well:

**File**: `~/Library/Application Support/Claude/claude_desktop_config.json`
```json
{
  "mcpServers": {
    "openbrain": {
      "command": "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway/.venv/bin/python",
      "args": ["-m", "src.main"],
      "cwd": "/Users/gniewkob/Repos/openbrain/unified/mcp-gateway",
      "env": {
        "BRAIN_URL": "http://127.0.0.1:7010",
        "INTERNAL_API_KEY": "set-a-unique-local-key-if-public-mode-is-enabled",
        "ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"
      }
    }
  }
}
```

`ENABLE_LOCAL_OBSIDIAN_TOOLS=1` should be set only for a trusted local `stdio` gateway on a machine that is allowed to read local Obsidian vaults. Leave it unset for generic MCP clients.

If Codex returns `404`, first verify that the `brain` server uses the `stdio` gateway above and not `url = "http://localhost:7010/sse"`.

Only use the direct local `http://localhost:7010/sse` endpoint for clients that can attach the required auth headers themselves. Claude Desktop cannot do that reliably in `PUBLIC_MODE=true`, which is why `stdio` is the recommended local configuration there.

### ChatGPT (Remote)
1. Check the URL using `./start_unified.sh status`.
2. In ChatGPT (**Settings > MCP**) add a new server:
   - **Name**: `OpenBrain`
   - **URL**: `https://[YOUR-ID].ngrok-free.app` (use the base URL, system redirects to /sse)
   - **Authentication**: OAuth (if PUBLIC_MODE=true) or X-Internal-Key (Header).

### Public Mode Requirements
- `PUBLIC_MODE=true` now fails closed.
- `OIDC_ISSUER_URL` is mandatory.
- `INTERNAL_API_KEY` must be explicitly configured and must not use the dev default. The key is compared with `hmac.compare_digest` — timing attacks against the key are not viable.
- `/health` and `/metrics` require authentication in public mode.
- For infrastructure probes and uptime checks, use `/healthz` and `/readyz`, not `/health`.

### Optional Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SOURCE_SYSTEM` | `other` | Tags every `brain_store` record with the calling agent (`claude`, `chatgpt`, `codex`, etc.) |
| `ENABLE_HTTP_OBSIDIAN_TOOLS` | `false` | Expose Obsidian sync tools via the HTTP MCP transport |
| `BACKEND_TIMEOUT_S` | `30` | Timeout (seconds) for MCP gateway → backend HTTP calls |
| `OIDC_DISCOVERY_CACHE_S` | `600` | OIDC discovery document cache TTL |
| `POSTGRES_USER` | `postgres` | PostgreSQL username for the local compose stack |
| `POSTGRES_PASSWORD` | _empty_ | Set this explicitly for any shared or public deployment |
| `POSTGRES_DB` | `openbrain_unified` | PostgreSQL database name for the local compose stack |

---

## 5. Maintenance and Logs

```bash
./start_unified.sh logs       # Follow server output and ChatGPT requests
./start_unified.sh stop       # Gracefully stop all services
```

**"Session Terminated" errors:** These usually happen when the ngrok URL changes. Refresh the ChatGPT page or click `Refresh` in the MCP settings.

---

## 6. Tests

Run tests through the repo-level `Makefile` so the backend and gateway use their intended virtual environments instead of the shell's default `python`.

```bash
make bootstrap-unified-venv
make bootstrap-gateway-venv
make test-unified
make test-gateway
make test
```

## 7. Governance

Before using Tier 3 tools in production, read the operating policy in [docs/governance-layer.md](docs/governance-layer.md).

Minimum rules:
- `corporate` records are versioned, not overwritten.
- `upsert_bulk` should be used only with stable `match_key`.
- `maintain` must start with `dry_run=true`.
- retrieval quality depends on keeping duplicate rates bounded.
