#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANARY="${ROOT_DIR}/scripts/host_full_canary.sh"
LOG_DIR="${ROOT_DIR}/monitoring"
STDOUT_LOG="${HOST_CANARY_STDOUT_LOG:-${LOG_DIR}/host-full-canary-stdout.log}"
STATUS_LOG="${HOST_CANARY_STATUS_LOG:-${LOG_DIR}/host-full-canary-status.log}"
ENABLE_NOTIFY="${HOST_CANARY_NOTIFY:-1}"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

notify() {
  local title="$1"
  local message="$2"

  if [[ "${ENABLE_NOTIFY}" != "1" ]]; then
    return
  fi

  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${message}\" with title \"${title}\"" >/dev/null 2>&1 || true
  fi
}

mkdir -p "${LOG_DIR}"

tmp_output="$(mktemp)"
trap 'rm -f "${tmp_output}"' EXIT

rc=0
if "${CANARY}" >"${tmp_output}" 2>&1; then
  rc=0
else
  rc=$?
fi

{
  printf '\n[%s] host_full_canary rc=%s\n' "$(timestamp)" "${rc}"
  cat "${tmp_output}"
} >> "${STDOUT_LOG}"

case "${rc}" in
  0)
    printf '[%s] OK\n' "$(timestamp)" >> "${STATUS_LOG}"
    ;;
  1)
    printf '[%s] WARN\n' "$(timestamp)" >> "${STATUS_LOG}"
    notify "Host Canary Warning" "host_full_canary completed with warnings"
    ;;
  *)
    printf '[%s] FAIL\n' "$(timestamp)" >> "${STATUS_LOG}"
    notify "Host Canary Failure" "host_full_canary found hard failures"
    ;;
esac

exit "${rc}"
