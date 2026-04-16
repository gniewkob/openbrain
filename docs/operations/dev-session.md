# Dev Session Guide: OpenBrain

## Stack separation

OpenBrain distinguishes between two layers of tooling:

| Layer | Compose file | Purpose | When to run |
|---|---|---|---|
| **Production core** | `docker-compose.unified.yml` | OpenBrain itself — DB, API, MCP gateway | Always |
| **Dev tools** | `docker-compose.mcp-dev.yml` | MCP servers supporting development, code review, web scraping | Dev sessions only |

The production core starts automatically and has no dev dependencies. The dev tools layer is opt-in.

## Starting a dev session

```bash
# 1. Production core (if not already running)
./start_unified.sh start

# 2. Dev MCP tools
docker compose -f docker-compose.mcp-dev.yml up -d
```

## Stopping a dev session

```bash
# Stop dev tools after the session
docker compose -f docker-compose.mcp-dev.yml down

# Production core keeps running
```

## Dev MCP tools — what each does

### HTTP servers (persistent, stay running)

| Container | Image | Purpose |
|---|---|---|
| `openbrain-mcp-context7` | `mcp/context7` | Library and framework docs lookup — use in Claude Code when working with any external library |
| `openbrain-mcp-node-code-sandbox` | `mcp/node-code-sandbox` | Isolated Node.js execution sandbox for testing JS/TS snippets |

### stdio servers (on-demand, exit when not connected)

| Container | Image | Purpose |
|---|---|---|
| `openbrain-mcp-playwright` | `mcp/playwright` | Browser automation for UI/E2E testing and visual inspection |
| `openbrain-mcp-markitdown` | `mcp/markitdown` | Convert PDFs, DOCX, HTML → markdown for ingestion into OpenBrain |
| `openbrain-mcp-desktop-commander` | `mcp/desktop-commander` | Terminal and desktop control — running commands, reading output |
| `openbrain-mcp-firecrawl` | `mcp/firecrawl` | Web scraping and crawling; requires `FIRECRAWL_API_KEY` in `.env` |

stdio servers are spawned on-demand by Claude Desktop / Docker Desktop MCP toolkit and exit cleanly when the session ends. They do not restart automatically.

## What is NOT in the dev stack (and why)

| Removed service | Reason |
|---|---|
| `mcp/memory` | Replaced by OpenBrain entirely — do not use |
| `mcp/obsidian` | Replaced by `mcpvault` CLI (`mcpvault /path/to/vault`) |
| `mcp/sequentialthinking` | Prompt technique only, no actual tooling value as a container |
| `mcp/atlassian` | No credentials configured; use Atlassian plugin in Claude Code instead |
| `mcp/youtube-transcript` | Niche use; pull image on demand if needed |
| `mcp/filesystem` | Claude Code has native file tools; redundant |

## Production core — services

Managed exclusively by `start_unified.sh`. Do not add dev tooling here.

| Service | Container | Role |
|---|---|---|
| PostgreSQL + pgvector | `openbrain-unified-db` | Persistent storage + vector search |
| Redis | `openbrain-unified-redis` | OAuth token cache |
| FastAPI server | `openbrain-unified-server` | REST API + MCP unified server (port 7010) |
| MCP HTTP gateway | `openbrain-mcp-http` | HTTP MCP transport for Claude Desktop / ChatGPT (`--profile public`) |
| ngrok | `openbrain-unified-ngrok` | External tunnel (`ENABLE_NGROK=1`, `--profile public`) |
| Ollama | local (macOS) | Embeddings via `nomic-embed-text`; not in Docker |
