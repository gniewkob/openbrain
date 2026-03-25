# OpenBrain Unified (v2.1)

OpenBrain is an intelligent, unified memory platform that serves as a semantic bridge between your personal knowledge (e.g., Obsidian) and Large Language Models (ChatGPT, Claude, Gemini).

It provides a governed, domain-aware vector store that allows AI agents to store, retrieve, and synthesize information with high precision and metadata integrity.

## Key Features

- **Unified Backend**: A single PostgreSQL + `pgvector` instance managing all your knowledge domains.
- **Model Context Protocol (MCP)**: Full support for the MCP standard, enabling seamless integration with Claude Desktop and ChatGPT.
- **Domain Governance**: 
  - `corporate`: Append-only versioning and audit trails for professional work.
  - `build`: Mutable store for technical projects and code.
  - `personal`: Lightweight store for private notes and ideas.
- **Industrial Routing**: Robust ASGI wrapper handling both MCP Transport (SSE) and OAuth Discovery (`.well-known`) out of the box.
- **Hybrid Search**: Combines semantic vector search with structured metadata filtering.

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
3. Start the system:
   ```bash
   ./start_unified.sh start
   ```

## Documentation

- [Installation & Configuration](INSTALLATION.md)
- [Operating Manual](docs/operating-manual.md)
- [API Architecture](docs/README.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
