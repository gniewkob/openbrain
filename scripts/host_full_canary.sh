#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_CANARY="${ROOT_DIR}/scripts/host_dual_canary.sh"
RESOURCE_CANARY="${ROOT_DIR}/scripts/host_resource_canary.sh"

STATUS=0

section() {
  printf '\n== %s ==\n' "$1"
}

run_canary() {
  local name="$1"
  local script_path="$2"
  local rc=0

  if [[ ! -x "${script_path}" ]]; then
    printf 'FAIL %s missing or not executable: %s\n' "${name}" "${script_path}"
    STATUS=2
    return
  fi

  section "${name}"
  if "${script_path}"; then
    printf 'OK   %s passed\n' "${name}"
    return
  fi

  rc=$?
  if [[ "${rc}" -eq 1 ]]; then
    printf 'WARN %s completed with warnings\n' "${name}"
    if [[ "${STATUS}" -lt 1 ]]; then
      STATUS=1
    fi
  else
    printf 'FAIL %s failed\n' "${name}"
    STATUS=2
  fi
}

main() {
  run_canary "service canary" "${SERVICE_CANARY}"
  run_canary "resource canary" "${RESOURCE_CANARY}"

  section "summary"
  case "${STATUS}" in
    0)
      printf 'OK   full host canary passed\n'
      ;;
    1)
      printf 'WARN full host canary completed with warnings\n'
      ;;
    *)
      printf 'FAIL full host canary found hard failures\n'
      ;;
  esac

  exit "${STATUS}"
}

main "$@"
