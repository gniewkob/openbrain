#!/usr/bin/env bash
# ============================================================
# OpenBrain v2.0 Unified — startup script
# Usage:  ./start_unified.sh [start|stop|status|logs]
# Default: start
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC}  $*" >&2; }
info() { echo -e "${CYAN}→${NC}  $*"; }

# Load .env if it exists
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
    ok "Loaded .env"
fi

compose_up() {
    info "Starting Unified OpenBrain (PostgreSQL + FastMCP) ..."
    docker compose -f docker-compose.unified.yml up -d --build
    ok "Containers started."
    info "Note: MCP Gateway runs on port 80 inside the unified-server container."
}

compose_down() {
    info "Stopping Unified OpenBrain ..."
    docker compose -f docker-compose.unified.yml down
    ok "All services stopped."
}

cmd_status() {
    echo ""
    echo -e "${CYAN}─── OpenBrain Unified Status ───────────────────────────${NC}"
    docker compose -f docker-compose.unified.yml ps
    echo ""
    
    local public_url="(waiting for ngrok...)"
    if [ "$(docker ps -q -f name=openbrain-unified-ngrok)" ]; then
        # Try fetching via internal Docker API from unified-server container
        public_url=$(docker exec openbrain-unified-server curl -s http://ngrok:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || \
                     curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || \
                     docker logs openbrain-unified-ngrok 2>&1 | grep -o 'https://[a-zA-Z0-9.-]*\.ngrok-free.app' | tail -n 1 || \
                     echo -e "${YELLOW}(waiting for ngrok...)${NC}")
    fi

    echo -e "${GREEN}Local (Claude Desktop):${NC}   http://localhost:7010"
    echo -e "${GREEN}External (ChatGPT):${NC}    ${public_url}"
    echo -e "${GREEN}Prometheus:${NC}            http://localhost:9090"
    echo -e "${GREEN}Grafana:${NC}               http://localhost:${GRAFANA_PORT:-3001}"
    echo ""
    echo -e "${CYAN}─── MCP Configuration Guide ────────────────────────────${NC}"
    echo "1. Claude Desktop (local): Use http://localhost:7010"
    echo "2. ChatGPT/Custom (external): Use ${public_url}"
    echo ""
    echo -e "Available Domains: ${YELLOW}corporate, build, personal${NC}"
    echo -e "Capabilities:      ${YELLOW}brain_capabilities (RUN THIS FIRST)${NC}"
    echo -e "HTTP MCP Tools:    ${YELLOW}brain_store, brain_get, brain_list, brain_search, brain_update, brain_delete,${NC}"
    echo -e "                   ${YELLOW}brain_get_context, brain_sync_check, brain_store_bulk,${NC}"
    echo -e "                   ${YELLOW}brain_upsert_bulk, brain_export, brain_maintain${NC}"
    echo -e "Local-only Tools:  ${YELLOW}brain_obsidian_vaults, brain_obsidian_read_note, brain_obsidian_sync${NC}"
    echo -e "Grafana Login:     ${YELLOW}${GRAFANA_ADMIN_USER:-admin} / ${GRAFANA_ADMIN_PASSWORD:-admin}${NC}"
    echo ""
}

cmd_logs() {
    docker compose -f docker-compose.unified.yml logs -f --tail 50
}

MODE="${1:-start}"
case "$MODE" in
    start)  compose_up; cmd_status ;;
    stop)   compose_down ;;
    status) cmd_status ;;
    logs)   cmd_logs ;;
    *)
        echo "Usage: $0 [start|stop|status|logs]"
        exit 1
        ;;
esac
