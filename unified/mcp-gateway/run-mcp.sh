#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
cd "$SCRIPT_DIR"

# Safe way to load .env without breaking on JSON/spaces
if [ -f "../../.env" ]; then
  set -a
  source <(grep -v '^#' ../../.env | sed 's/\r$//')
  set +a
fi

# Fix PYTHONPATH: add unified/src directly to avoid 'src' naming conflict
export PYTHONPATH=$(pwd)/../src:$PYTHONPATH

# Run the MCP server
source .venv/bin/activate
exec python3 -m src.main
