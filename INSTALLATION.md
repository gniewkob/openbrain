# OpenBrain v2.1 — Installation and Configuration Guide

> Version: 2.1 (Industrial)

---

## Architecture

```
Local Clients (Claude Desktop) ──┐
                                 ├─→ unified-server (:7010) ─→ PostgreSQL + pgvector
Remote Clients (ChatGPT) ────────┤          ↑ (SSE / JSON-RPC)        ↑
                                 └─→ ngrok ─┘                  Ollama (embed)
```

- **Backend**: FastAPI + FastMCP in Docker (port 7010).
- **Industrial Wrapper**: Stable ASGI routing handling MCP and OAuth Discovery automatically.
- **Domains**: `corporate` (append-only), `build` (projects), `personal` (private).

---

## 1. Startup

```bash
cd ~/Repos/openbrain
./start_unified.sh start     # Starts all services: DB + Ollama + Server + Ngrok
./start_unified.sh status    # Check status and view current URLs
```

**Note:** ngrok starts **by default**. The public URL for ChatGPT changes on every restart (unless you have a static ngrok domain).

---

## 2. MCP Tools (12 + 1 Diagnostic)

The system uses intent-based descriptions ("Use when / Do not use when") to guide AI models.

### Tier 0: Diagnostics
- `brain_capabilities`: Check runtime status and tool availability. **Run this first in a new session.**

### Tier 1: Core (Daily Work)
- `brain_search`: Semantic search (primary tool).
- `brain_get`: Retrieve a specific record by ID.
- `brain_store`: Save a single note/decision.
- `brain_update`: Update an existing record.

### Tier 2: Advanced (Specialized)
- `brain_list`: Browse the database with filters (domain, owner).
- `brain_get_context`: Build a synthetic context pack from multiple records.
- `brain_delete`: Delete (allowed ONLY for `build` and `personal` domains).
- `brain_export`: Export data to JSON (redacts sensitive content).
- `brain_sync_check`: Verify consistency with Obsidian (hash check).

### Tier 3: Admin (High Risk)
- `brain_store_bulk`: Batch save (up to 50 records).
- `brain_upsert_bulk`: Intelligent synchronization (`match_key` based).
- `brain_maintain`: System maintenance (deduplication, link fixing).

---

## 3. Client Configuration

### Claude Desktop (Local)
In your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "openbrain": {
      "url": "http://localhost:7010/sse"
    }
  }
}
```

### ChatGPT (Remote)
1. Check the URL using `./start_unified.sh status`.
2. In ChatGPT (**Settings > MCP**) add a new server:
   - **Name**: `OpenBrain`
   - **URL**: `https://[YOUR-ID].ngrok-free.app` (use the base URL, system redirects to /sse)
   - **Authentication**: OAuth (if PUBLIC_MODE=true) or X-Internal-Key (Header).

---

## 4. Maintenance and Logs

```bash
./start_unified.sh logs       # Follow server output and ChatGPT requests
./start_unified.sh stop       # Gracefully stop all services
```

**"Session Terminated" errors:** These usually happen when the ngrok URL changes. Refresh the ChatGPT page or click `Refresh` in the MCP settings.
