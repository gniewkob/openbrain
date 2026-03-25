#!/usr/bin/env bash
# Relative path to the gateway directory
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
cd "$SCRIPT_DIR"

# Run the MCP server using the local virtual environment
source .venv/bin/activate
exec python3 -m src.main
