#!/usr/bin/env bash

set -euo pipefail

DISK_WARN_PCT="${DISK_WARN_PCT:-85}"
DISK_FAIL_PCT="${DISK_FAIL_PCT:-95}"
LOAD_WARN_PER_CPU="${LOAD_WARN_PER_CPU:-1.5}"
LOAD_FAIL_PER_CPU="${LOAD_FAIL_PER_CPU:-3.0}"
SWAPOUT_WARN_PAGES="${SWAPOUT_WARN_PAGES:-20000000}"
SWAPOUT_FAIL_PAGES="${SWAPOUT_FAIL_PAGES:-50000000}"

STATUS=0

section() {
  printf '\n== %s ==\n' "$1"
}

ok() {
  printf 'OK   %s\n' "$1"
}

warn() {
  printf 'WARN %s\n' "$1"
  if [[ "${STATUS}" -lt 1 ]]; then
    STATUS=1
  fi
}

fail() {
  printf 'FAIL %s\n' "$1"
  STATUS=2
}

require_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    fail "Missing required command: ${cmd}"
    exit 2
  fi
}

check_disk() {
  local used_pct
  used_pct="$(df -Pk / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
  if [[ -z "${used_pct}" ]]; then
    fail "disk usage check failed"
    return
  fi
  if (( used_pct >= DISK_FAIL_PCT )); then
    fail "root filesystem usage ${used_pct}%"
  elif (( used_pct >= DISK_WARN_PCT )); then
    warn "root filesystem usage ${used_pct}%"
  else
    ok "root filesystem usage ${used_pct}%"
  fi
}

check_load() {
  local cpus load1 threshold_warn threshold_fail
  cpus="$(sysctl -n hw.ncpu 2>/dev/null || true)"
  load1="$(uptime | awk -F'load averages?: ' '{print $2}' | awk -F'[, ]+' '{print $1}')"

  if [[ -z "${cpus}" || -z "${load1}" ]]; then
    warn "load average unavailable"
    return
  fi

  threshold_warn="$(awk -v cpu="${cpus}" -v mul="${LOAD_WARN_PER_CPU}" 'BEGIN {printf "%.2f", cpu * mul}')"
  threshold_fail="$(awk -v cpu="${cpus}" -v mul="${LOAD_FAIL_PER_CPU}" 'BEGIN {printf "%.2f", cpu * mul}')"

  if awk -v load="${load1}" -v thr="${threshold_fail}" 'BEGIN {exit !(load >= thr)}'; then
    fail "load1 ${load1} on ${cpus} CPUs"
  elif awk -v load="${load1}" -v thr="${threshold_warn}" 'BEGIN {exit !(load >= thr)}'; then
    warn "load1 ${load1} on ${cpus} CPUs"
  else
    ok "load1 ${load1} on ${cpus} CPUs"
  fi
}

check_vm_pressure() {
  local vm_output page_size pages_free pages_speculative pages_active pages_inactive pages_wired swapouts free_bytes total_bytes free_ratio
  vm_output="$(vm_stat)"
  page_size="$(awk -F'page size of ' 'NR==1 {gsub(/[^0-9]/, "", $2); print $2}' <<<"${vm_output}")"
  pages_free="$(awk '/Pages free/ {gsub(/\./, "", $3); print $3}' <<<"${vm_output}")"
  pages_speculative="$(awk '/Pages speculative/ {gsub(/\./, "", $3); print $3}' <<<"${vm_output}")"
  pages_active="$(awk '/Pages active/ {gsub(/\./, "", $3); print $3}' <<<"${vm_output}")"
  pages_inactive="$(awk '/Pages inactive/ {gsub(/\./, "", $3); print $3}' <<<"${vm_output}")"
  pages_wired="$(awk '/Pages wired down/ {gsub(/\./, "", $4); print $4}' <<<"${vm_output}")"
  swapouts="$(awk '/Swapouts/ {gsub(/\./, "", $2); print $2}' <<<"${vm_output}")"

  if [[ -z "${page_size}" || -z "${pages_free}" || -z "${pages_speculative}" || -z "${pages_active}" || -z "${pages_inactive}" || -z "${pages_wired}" || -z "${swapouts}" ]]; then
    warn "vm_stat parsing incomplete"
    return
  fi

  free_bytes=$(( (pages_free + pages_speculative) * page_size ))
  total_bytes=$(( (pages_free + pages_speculative + pages_active + pages_inactive + pages_wired) * page_size ))
  free_ratio="$(awk -v free="${free_bytes}" -v total="${total_bytes}" 'BEGIN { if (total == 0) { print "0.00" } else { printf "%.2f", (free / total) * 100 } }')"

  if (( swapouts >= SWAPOUT_FAIL_PAGES )); then
    fail "swapouts high: ${swapouts} pages, free memory ${free_ratio}%"
  elif (( swapouts >= SWAPOUT_WARN_PAGES )); then
    warn "swapouts elevated: ${swapouts} pages, free memory ${free_ratio}%"
  elif awk -v free="${free_ratio}" 'BEGIN {exit !(free < 3.0)}'; then
    warn "free memory low: ${free_ratio}%"
  else
    ok "vm pressure acceptable: free memory ${free_ratio}%, swapouts ${swapouts}"
  fi
}

check_docker() {
  local info
  if ! info="$(docker info --format '{{.ServerVersion}} {{.ContainersRunning}} {{.ContainersPaused}} {{.ContainersStopped}}' 2>/dev/null)"; then
    warn "docker info unavailable from current shell"
    return
  fi
  ok "docker healthy: ${info}"
}

check_launchd_services() {
  local labels
  labels="$(launchctl list | grep -E 'com.mailai|com.openbrain' || true)"
  if [[ -z "${labels}" ]]; then
    warn "no mailai/openbrain launchd labels found"
    return
  fi
  ok "launchd labels present"
  printf '%s\n' "${labels}"
}

check_restart_symptoms() {
  local output
  output="$(ps -axo pid,ppid,state,etime,command | grep -E 'mail_ai_agent|metrics_bridge|openbrain-unified|ollama' | grep -v grep || true)"
  if [[ -z "${output}" ]]; then
    warn "no tracked service processes found in ps snapshot"
    return
  fi
  ok "tracked service processes present"
  printf '%s\n' "${output}"
}

main() {
  require_command df
  require_command vm_stat
  require_command uptime
  require_command launchctl
  require_command ps
  require_command docker

  section "disk"
  check_disk

  section "load"
  check_load

  section "memory"
  check_vm_pressure

  section "docker"
  check_docker

  section "launchd"
  check_launchd_services

  section "process snapshot"
  check_restart_symptoms

  section "summary"
  case "${STATUS}" in
    0)
      printf 'OK   host resource canary passed\n'
      ;;
    1)
      printf 'WARN host resource canary completed with warnings\n'
      ;;
    *)
      printf 'FAIL host resource canary found hard failures\n'
      ;;
  esac

  exit "${STATUS}"
}

main "$@"
