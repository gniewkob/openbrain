# OpenBrain Unified

![Tests](https://img.shields.io/badge/tests-1403%20passed-brightgreen) ![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen) ![Python](https://img.shields.io/badge/python-3.12%2B-blue)

OpenBrain is an intelligent, unified memory platform that serves as a semantic bridge between your personal knowledge (e.g., Obsidian) and Large Language Models (ChatGPT, Claude, Gemini).

It provides a governed, domain-aware vector store that allows AI agents to store, retrieve, and synthesize information with high precision and metadata integrity.

By default the local stack binds service ports to `127.0.0.1`, not all interfaces. That is intentional: the compose file is optimized for local development first, and public exposure should happen through an explicit ingress layer such as ngrok or a reverse proxy.

## Key Features

- **Performance Optimized**: 
  - **Direct Filesystem Access**: Blazing fast Obsidian note reading by bypassing CLI and reading directly from disk.
  - **Parallel Processing**: Asynchronous parallel processing for note synchronization and embedding generation.
  - **Aggressive Caching**: Intelligent LRU caching for embeddings with automatic circuit breaker for Ollama availability.

- **Unified Backend**: A single PostgreSQL + `pgvector` instance managing all your knowledge domains.
- **Model Context Protocol (MCP)**: Full support for the MCP standard, enabling seamless integration with Claude Desktop and ChatGPT.
- **Domain Governance**:
  - `corporate`: Append-only versioning and audit trails for professional work. `brain_store` and `upsert_bulk` work correctly for all domains.
  - `build`: Mutable store for technical projects and code.
  - `personal`: Lightweight store for private notes and ideas.
- **Industrial Routing**: Robust ASGI wrapper handling MCP Transport (SSE), OAuth Discovery (`.well-known`), and Swagger UI (`/docs`) — all routed to the authoritative FastAPI handler.
- **Hybrid Search**: Combines semantic vector search with structured metadata filtering.
- **Security Hardened**: Timing-safe `X-Internal-Key` comparison, thread-safe policy registry, SQL-based O(n) dedup.
- **Truthful Health Reporting**:
  - `brain_capabilities` distinguishes an unreachable backend from a reachable-but-degraded backend.
  - `/healthz` is liveness-only, while `/readyz` carries subsystem readiness (`db`, `vector_store`).
  - Local Obsidian tools are listed explicitly and appear only when `ENABLE_LOCAL_OBSIDIAN_TOOLS=1`.

## Quick Start

### Prerequisites
- Docker & Docker Compose
- [Ollama](https://ollama.ai/) (for local embeddings)
- [ngrok](https://ngrok.com/) (for remote access via ChatGPT)

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/openbrain.git
   cd openbrain
   ```
2. Configure your environment:
   ```bash
   cp .env.example .env
   # Edit .env with your NGROK_AUTHTOKEN and other settings
   ```
   In `PUBLIC_MODE=true`, OpenBrain now fails closed:
   - `OIDC_ISSUER_URL` must be set
   - `INTERNAL_API_KEY` must be set to a non-default secret
   - `/health` and `/metrics` require authentication
   - use `/healthz` for liveness and `/readyz` for readiness probes
   - authenticated identity is the source of truth for audit actors during updates; request-level `updated_by` is compatibility metadata, not an override
3. Start the system:
   ```bash
   ./start_unified.sh start
   ```

## Tests

Use the repo-level `Makefile` so tests always run with the intended interpreter instead of whichever `python` happens to be first in `PATH`.

```bash
make bootstrap-unified-venv
make bootstrap-gateway-venv
make test-unified
make test-gateway
make test
```

Before opening a PR, run the consolidated static guardrails:

```bash
python3 scripts/check_local_guardrails.py
```

For a broader local pre-PR sanity bundle (guardrails + policy/contract smoke tests):

```bash
make pr-readiness
```

## Documentation

- [Current Status (2026-04-14)](docs/STATUS_2026-04-14.md)
- [Installation & Configuration](INSTALLATION.md)
- [Operating Manual](docs/operating-manual.md)
- [Governance Layer](docs/governance-layer.md)
- [API Architecture](docs/README.md)
- [Architecture Decisions](docs/adr/)
- [Improvement Roadmap Q2 2026](docs/IMPROVEMENT_ROADMAP_2026-Q2.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
