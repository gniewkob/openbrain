#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_CANARY="${ROOT_DIR}/scripts/host_dual_canary.sh"
RESOURCE_CANARY="${ROOT_DIR}/scripts/host_resource_canary.sh"
LOG_DIR="${ROOT_DIR}/monitoring"
STDOUT_LOG="${HOST_CANARY_STDOUT_LOG:-${LOG_DIR}/host-full-canary-stdout.log}"
STATUS_LOG="${HOST_CANARY_STATUS_LOG:-${LOG_DIR}/host-full-canary-status.log}"
METRICS_FILE="${HOST_CANARY_METRICS_FILE:-${LOG_DIR}/host-full-canary.prom}"
ENABLE_NOTIFY="${HOST_CANARY_NOTIFY:-1}"

default_host_label() {
  hostname -s | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/_/g; s/^_+//; s/_+$//'
}

HOST_LABEL="${HOST_CANARY_HOST_LABEL:-$(default_host_label)}"

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

severity_label() {
  case "$1" in
    0) printf 'OK' ;;
    1) printf 'WARN' ;;
    *) printf 'FAIL' ;;
  esac
}

max_severity() {
  local current="$1"
  local candidate="$2"
  if (( candidate > current )); then
    printf '%s' "${candidate}"
  else
    printf '%s' "${current}"
  fi
}

run_canary() {
  local script_path="$1"
  local output_path="$2"
  local rc=0

  if "${script_path}" >"${output_path}" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  printf '%s' "${rc}"
}

derive_component_severity() {
  local output_path="$1"
  local component="$2"
  local severity=0
  local line candidate

  while IFS= read -r line; do
    candidate=0
    [[ "${line}" == WARN* ]] && candidate=1
    [[ "${line}" == FAIL* ]] && candidate=2
    if (( candidate == 0 )); then
      continue
    fi
    if [[ "${line,,}" == *"${component}"* ]]; then
      severity="$(max_severity "${severity}" "${candidate}")"
    fi
  done < "${output_path}"

  printf '%s' "${severity}"
}

write_metrics() {
  local full_rc="$1"
  local service_rc="$2"
  local resource_rc="$3"
  local openbrain_rc="$4"
  local mailai_rc="$5"
  local host_rc="$6"
  local now_epoch="$7"
  local tmp_metrics

  tmp_metrics="$(mktemp)"
  {
    printf '# HELP macmini_canary_status Host canary severity where 0=ok, 1=warn, 2=fail.\n'
    printf '# TYPE macmini_canary_status gauge\n'
    printf 'macmini_canary_status{host="%s",scope="full"} %s\n' "${HOST_LABEL}" "${full_rc}"
    printf 'macmini_canary_status{host="%s",scope="service"} %s\n' "${HOST_LABEL}" "${service_rc}"
    printf 'macmini_canary_status{host="%s",scope="resource"} %s\n' "${HOST_LABEL}" "${resource_rc}"
    printf '# HELP macmini_canary_component_status Component-specific canary severity where 0=ok, 1=warn, 2=fail.\n'
    printf '# TYPE macmini_canary_component_status gauge\n'
    printf 'macmini_canary_component_status{host="%s",component="openbrain"} %s\n' "${HOST_LABEL}" "${openbrain_rc}"
    printf 'macmini_canary_component_status{host="%s",component="mailai"} %s\n' "${HOST_LABEL}" "${mailai_rc}"
    printf 'macmini_canary_component_status{host="%s",component="host"} %s\n' "${HOST_LABEL}" "${host_rc}"
    printf '# HELP macmini_canary_last_run_timestamp_seconds Unix timestamp of the last host canary execution.\n'
    printf '# TYPE macmini_canary_last_run_timestamp_seconds gauge\n'
    printf 'macmini_canary_last_run_timestamp_seconds{host="%s"} %s\n' "${HOST_LABEL}" "${now_epoch}"
  } > "${tmp_metrics}"
  mv "${tmp_metrics}" "${METRICS_FILE}"
}

mkdir -p "${LOG_DIR}"

tmp_service_output="$(mktemp)"
tmp_resource_output="$(mktemp)"
trap 'rm -f "${tmp_service_output}" "${tmp_resource_output}"' EXIT

service_rc="$(run_canary "${SERVICE_CANARY}" "${tmp_service_output}")"
resource_rc="$(run_canary "${RESOURCE_CANARY}" "${tmp_resource_output}")"
full_rc="${service_rc}"
if (( resource_rc > full_rc )); then
  full_rc="${resource_rc}"
fi

openbrain_rc="$(derive_component_severity "${tmp_service_output}" "openbrain")"
mailai_rc="$(derive_component_severity "${tmp_service_output}" "mailai")"
host_rc="${resource_rc}"
now_iso="$(timestamp)"
now_epoch="$(date -u +%s)"

write_metrics "${full_rc}" "${service_rc}" "${resource_rc}" "${openbrain_rc}" "${mailai_rc}" "${host_rc}" "${now_epoch}"

{
  printf '\n[%s] host_full_canary rc=%s\n' "${now_iso}" "${full_rc}"
  printf '\n== service canary ==\n'
  cat "${tmp_service_output}"
  printf '%s service canary %s\n' "$(severity_label "${service_rc}")" "$(
    if (( service_rc == 0 )); then
      printf 'passed'
    elif (( service_rc == 1 )); then
      printf 'completed with warnings'
    else
      printf 'failed'
    fi
  )"
  printf '\n== resource canary ==\n'
  cat "${tmp_resource_output}"
  printf '%s resource canary %s\n' "$(severity_label "${resource_rc}")" "$(
    if (( resource_rc == 0 )); then
      printf 'passed'
    elif (( resource_rc == 1 )); then
      printf 'completed with warnings'
    else
      printf 'failed'
    fi
  )"
  printf '\n== summary ==\n'
  printf '%s full host canary %s\n' "$(severity_label "${full_rc}")" "$(
    if (( full_rc == 0 )); then
      printf 'passed'
    elif (( full_rc == 1 )); then
      printf 'completed with warnings'
    else
      printf 'found hard failures'
    fi
  )"
} >> "${STDOUT_LOG}"

case "${full_rc}" in
  0)
    printf '[%s] OK\n' "${now_iso}" >> "${STATUS_LOG}"
    ;;
  1)
    printf '[%s] WARN\n' "${now_iso}" >> "${STATUS_LOG}"
    notify "Host Canary Warning" "host_full_canary completed with warnings"
    ;;
  *)
    printf '[%s] FAIL\n' "${now_iso}" >> "${STATUS_LOG}"
    notify "Host Canary Failure" "host_full_canary found hard failures"
    ;;
esac

exit "${full_rc}"
