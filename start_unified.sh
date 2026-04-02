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

is_true() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

compose_cmd() {
    local args=(-f docker-compose.unified.yml)
    if is_true "${ENABLE_NGROK:-false}"; then
        args+=(--profile public)
    fi
    docker compose "${args[@]}" "$@"
}

compose_cmd_public() {
    docker compose -f docker-compose.unified.yml --profile public "$@"
}

compose_cmd_base() {
    docker compose -f docker-compose.unified.yml "$@"
}

validate_runtime_security() {
    local public_mode="${PUBLIC_MODE:-false}"
    local public_base_url="${PUBLIC_BASE_URL:-}"
    local p_def="postgres"
    local a_def="admin"
    local db_def="openbrain_unified"

    # Export defaults if missing from environment
    export POSTGRES_USER="${POSTGRES_USER:-$p_def}"
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$p_def}"
    export POSTGRES_DB="${POSTGRES_DB:-$db_def}"
    export GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-$a_def}"
    export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-$a_def}"

    local shared_or_public=false
    if is_true "$public_mode" || [ -n "$public_base_url" ]; then
        shared_or_public=true
    fi

    if [ "$shared_or_public" = true ]; then
        if [ "$POSTGRES_USER" = "$p_def" ] && [ "$POSTGRES_PASSWORD" = "$p_def" ]; then
            err "PUBLIC_MODE/public exposure forbids default PostgreSQL credentials."
            err "Set POSTGRES_USER/POSTGRES_PASSWORD in .env before starting."
            exit 1
        fi
        if [ "$GRAFANA_ADMIN_USER" = "$a_def" ] && [ "$GRAFANA_ADMIN_PASSWORD" = "$a_def" ]; then
            err "PUBLIC_MODE/public exposure forbids default Grafana credentials."
            err "Set GRAFANA_ADMIN_USER/GRAFANA_ADMIN_PASSWORD in .env before starting."
            exit 1
        fi
    else
        if [ "$POSTGRES_USER" = "$p_def" ] && [ "$POSTGRES_PASSWORD" = "$p_def" ]; then
            warn "Using default PostgreSQL credentials for local dev only."
        fi
        if [ "$GRAFANA_ADMIN_USER" = "$a_def" ] && [ "$GRAFANA_ADMIN_PASSWORD" = "$a_def" ]; then
            warn "Using default Grafana credentials for local dev only."
        fi
    fi
}

# Load .env if it exists
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
    ok "Loaded .env"
fi

compose_up() {
    validate_runtime_security
    info "Starting Unified OpenBrain (PostgreSQL + FastMCP) ..."
    if is_true "${ENABLE_NGROK:-false}"; then
        info "Public tunnel enabled via ENABLE_NGROK=1 (Compose profile: public)."
    else
        info "Ngrok profile disabled; starting local-only stack."
    fi
    compose_cmd up -d --build
    ok "Containers started."
    info "Note: MCP Gateway runs on port 80 inside the unified-server container."
}

compose_down() {
    info "Stopping Unified OpenBrain ..."
    # Always tear down the public profile too. Otherwise a stack started with
    # ENABLE_NGROK=1 can leave the ngrok container attached to the network when
    # stop is later invoked without that env flag.
    compose_cmd_public down
    compose_cmd_base down
    ok "All services stopped."
}

cmd_status() {
    echo ""
    echo -e "${CYAN}─── OpenBrain Unified Status ───────────────────────────${NC}"
    compose_cmd ps
    echo ""
    
    local public_url="${YELLOW}(ngrok profile disabled; set ENABLE_NGROK=1)${NC}"
    local public_url_plain="(ngrok profile disabled; set ENABLE_NGROK=1)"
    if [ "$(docker ps -q -f name=openbrain-unified-ngrok)" ]; then
        public_url="${PUBLIC_BASE_URL:-"(waiting for ngrok...)"}"
        public_url_plain="$public_url"
        # Try fetching via internal Docker API from unified-server container
        public_url=$(docker exec openbrain-unified-server curl -s http://ngrok:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || \
                     curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || \
                     docker logs openbrain-unified-ngrok 2>&1 | grep -o 'https://[a-zA-Z0-9.-]*\.ngrok-free.app' | tail -n 1 || \
                     echo "${PUBLIC_BASE_URL:-${YELLOW}(waiting for ngrok...)${NC}}")
        public_url_plain=$(printf '%s' "$public_url" | sed $'s/\033\\[[0-9;]*m//g')
    fi

    echo -e "${GREEN}Local (Claude Desktop):${NC}   http://localhost:7010"
    echo -e "${GREEN}External (ChatGPT):${NC}    ${public_url}"
    echo -e "${GREEN}Prometheus:${NC}            http://localhost:9090"
    echo -e "${GREEN}Grafana:${NC}               http://localhost:${GRAFANA_PORT:-3001}"
    echo ""
    echo -e "${CYAN}─── MCP Configuration Guide ────────────────────────────${NC}"
    echo "1. Claude Desktop (local): Use http://localhost:7010"
    echo "2. ChatGPT/Custom (external): Use ${public_url_plain}"
    echo ""
    echo -e "Available Domains: ${YELLOW}corporate, build, personal${NC}"
    echo -e "Capabilities:      ${YELLOW}brain_capabilities (RUN THIS FIRST)${NC}"
    echo -e "HTTP MCP Tools:    ${YELLOW}brain_store, brain_get, brain_list, brain_search, brain_update, brain_delete,${NC}"
    echo -e "                   ${YELLOW}brain_get_context, brain_sync_check, brain_store_bulk,${NC}"
    echo -e "                   ${YELLOW}brain_upsert_bulk, brain_export, brain_maintain${NC}"
    echo -e "Local-only Tools:  ${YELLOW}brain_obsidian_vaults, brain_obsidian_read_note, brain_obsidian_sync${NC}"
    echo -e "Grafana Login:     ${YELLOW}${GRAFANA_ADMIN_USER:-admin} / [hidden]${NC}"
    echo ""
}

cmd_logs() {
    compose_cmd logs -f --tail 50
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
