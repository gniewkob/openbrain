#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

OPENBRAIN_LOCAL_HEALTH_URL="${OPENBRAIN_LOCAL_HEALTH_URL:-http://127.0.0.1:7010/healthz}"
OPENBRAIN_LOCAL_READY_URL="${OPENBRAIN_LOCAL_READY_URL:-http://127.0.0.1:7010/readyz}"
OPENBRAIN_BRIDGE_METRICS_URL="${OPENBRAIN_BRIDGE_METRICS_URL:-http://127.0.0.1:9180/metrics}"
MAILAI_METRICS_URL="${MAILAI_METRICS_URL:-http://127.0.0.1:9177/metrics}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

OPENBRAIN_CONTAINERS=(
  openbrain-unified-server
  openbrain-unified-db
  openbrain-unified-prometheus
  openbrain-unified-grafana
  openbrain-unified-ollama
)

MAILAI_LAUNCHD_LABELS=(
  com.mailai.multi.prod
  com.mailai.metrics.prod
)

OPENBRAIN_LAUNCHD_LABELS=(
  com.openbrain.metrics.bridge
)

STATUS=0

section() {
  printf '\n== %s ==\n' "$1"
}

ok() {
  printf 'OK   %s\n' "$1"
}

warn() {
  printf 'WARN %s\n' "$1"
  STATUS=1
}

fail() {
  printf 'FAIL %s\n' "$1"
  STATUS=2
}

load_env_file() {
  if [[ -f "${ENV_FILE}" ]]; then
    while IFS='=' read -r key value; do
      [[ -z "${key}" ]] && continue
      [[ "${key}" =~ ^# ]] && continue
      if [[ "${key}" == "PUBLIC_BASE_URL" && -z "${PUBLIC_BASE_URL}" ]]; then
        value="${value%\"}"
        value="${value#\"}"
        PUBLIC_BASE_URL="${value}"
      fi
    done < "${ENV_FILE}"
  fi
}

require_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    fail "Missing required command: ${cmd}"
    exit 2
  fi
}

check_http_json_contains() {
  local name="$1"
  local url="$2"
  local needle="$3"
  local body
  if ! body="$(curl -fsS "${url}")"; then
    fail "${name}: ${url} unreachable"
    return
  fi
  if grep -Fq "${needle}" <<<"${body}"; then
    ok "${name}: ${url}"
  else
    fail "${name}: unexpected response from ${url}"
  fi
}

check_http_text_contains() {
  local name="$1"
  local url="$2"
  local needle="$3"
  local body
  if ! body="$(curl -fsS "${url}")"; then
    fail "${name}: ${url} unreachable"
    return
  fi
  if grep -Fq "${needle}" <<<"${body}"; then
    ok "${name}: ${url}"
  else
    fail "${name}: missing expected metric '${needle}'"
  fi
}

check_prometheus_target() {
  local job="$1"
  local body
  if ! body="$(curl -fsS "${PROMETHEUS_URL}/api/v1/query?query=up%7Bjob%3D%22${job}%22%7D")"; then
    fail "Prometheus query failed for job=${job}"
    return
  fi
  if grep -Fq '"value":[' <<<"${body}" && grep -Fq '"1"]' <<<"${body}"; then
    ok "Prometheus target up: ${job}"
  else
    fail "Prometheus target down or missing: ${job}"
  fi
}

check_launchd_label() {
  local label="$1"
  if launchctl list | awk '{print $3}' | grep -Fxq "${label}"; then
    ok "launchd label present: ${label}"
  else
    fail "launchd label missing: ${label}"
  fi
}

check_container_running() {
  local name="$1"
  if docker ps --format '{{.Names}}' | grep -Fxq "${name}"; then
    ok "container running: ${name}"
  else
    fail "container missing: ${name}"
  fi
}

check_public_openbrain() {
  if [[ -z "${PUBLIC_BASE_URL}" ]]; then
    warn "PUBLIC_BASE_URL not set; skipping public OpenBrain checks"
    return
  fi

  local health_body
  if health_body="$(curl -fsS "${PUBLIC_BASE_URL}/healthz")" && grep -Fq '"status":"ok"' <<<"${health_body}"; then
    ok "public openbrain healthz: ${PUBLIC_BASE_URL}/healthz"
  else
    fail "public openbrain healthz failed: ${PUBLIC_BASE_URL}/healthz"
  fi

  local sse_status
  if sse_status="$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_BASE_URL}/sse")" && [[ "${sse_status}" == "401" ]]; then
    ok "public openbrain sse protected: ${PUBLIC_BASE_URL}/sse -> 401"
  else
    fail "public openbrain sse protection unexpected: ${PUBLIC_BASE_URL}/sse -> ${sse_status:-error}"
  fi
}

main() {
  require_command curl
  require_command docker
  require_command launchctl

  load_env_file

  section "openbrain containers"
  for container in "${OPENBRAIN_CONTAINERS[@]}"; do
    check_container_running "${container}"
  done

  section "openbrain host checks"
  check_http_json_contains "openbrain healthz" "${OPENBRAIN_LOCAL_HEALTH_URL}" '"status":"ok"'
  check_http_json_contains "openbrain readyz" "${OPENBRAIN_LOCAL_READY_URL}" '"db":"ok"'
  check_http_text_contains "openbrain metrics bridge" "${OPENBRAIN_BRIDGE_METRICS_URL}" 'operational_health_status'

  section "mailai host checks"
  for label in "${MAILAI_LAUNCHD_LABELS[@]}"; do
    check_launchd_label "${label}"
  done
  check_http_text_contains "mailai metrics exporter" "${MAILAI_METRICS_URL}" 'operational_health_status'

  section "openbrain launchd bridge"
  for label in "${OPENBRAIN_LAUNCHD_LABELS[@]}"; do
    check_launchd_label "${label}"
  done

  section "prometheus targets"
  check_prometheus_target "openbrain-unified"
  check_prometheus_target "mailai"

  section "public openbrain"
  check_public_openbrain

  section "summary"
  case "${STATUS}" in
    0)
      printf 'OK   dual-system canary passed\n'
      ;;
    1)
      printf 'WARN dual-system canary completed with warnings\n'
      ;;
    *)
      printf 'FAIL dual-system canary found hard failures\n'
      ;;
  esac

  exit "${STATUS}"
}

main "$@"
