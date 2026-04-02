#!/usr/bin/env bash

set -euo pipefail

section() {
  printf '\n== %s ==\n' "$1"
}

section "docker ps"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

section "listening ports"
lsof -iTCP -sTCP:LISTEN -n -P

section "launchctl filtered"
launchctl list | grep -E 'openbrain|mailai|ollama' || true

section "openbrain status"
./start_unified.sh status

section "prometheus targets via container"
docker exec openbrain-unified-prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/targets'

