#!/usr/bin/env bash
set -euo pipefail

# Derive repo root from script location: scripts/ -> unified/ -> openbrain/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CFG_PATH="${OPENBRAIN_CONFIG:-$REPO_ROOT/.mcp.json}"
LOG_DIR="${OPENBRAIN_LOG_DIR:-$REPO_ROOT/unified/logs}"
LOG_FILE="$LOG_DIR/weekly_maintain_dry_run.log"

mkdir -p "$LOG_DIR"

if [[ ! -f "$CFG_PATH" ]]; then
  echo "$(date -Iseconds) ERROR config not found: $CFG_PATH" >> "$LOG_FILE"
  exit 1
fi

# Read both BASE_URL and API_KEY from config in a single python3 call.
read -r BASE_URL API_KEY < <(python3 - "$CFG_PATH" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)
env = data['mcpServers']['openbrain']['env']
print(env['BRAIN_URL'].rstrip('/'), env['INTERNAL_API_KEY'])
PY
)

TS="$(date -Iseconds)"
PAYLOAD='{"dry_run":true,"dedup_threshold":0.93,"fix_superseded_links":true,"normalize_owners":{"gniewkob":"Gniewko"}}'

RESP="$(curl -sS -m 30 \
  -H "Content-Type: application/json" \
  -H "X-Internal-Key: ${API_KEY}" \
  -X POST "${BASE_URL}/api/v1/memory/maintain" \
  -d "$PAYLOAD")"

# Single-line JSON log for easy grep/jq
printf '%s %s\n' "$TS" "$RESP" >> "$LOG_FILE"

# Optional brief status line
python3 - "$RESP" "$LOG_FILE" "$TS" <<'PY'
import json, sys
resp_raw = sys.argv[1]
log_file = sys.argv[2]
ts = sys.argv[3]
try:
    r = json.loads(resp_raw)
    summary = (
        f"{ts} SUMMARY dry_run={r.get('dry_run')} scanned={r.get('total_scanned')}"
        f" dedup={r.get('dedup_found')} owners={r.get('owners_normalized')}"
        f" links={r.get('links_fixed')}"
    )
except Exception:
    summary = f"{ts} SUMMARY parse_error"
with open(log_file, 'a', encoding='utf-8') as f:
    f.write(summary + '\n')
PY
