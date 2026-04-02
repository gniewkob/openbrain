#!/usr/bin/env bash

set -euo pipefail

APPLY=0
INCLUDE_RUNNING=0
MAX_RUNNING_AGE_HOURS="${MAX_RUNNING_AGE_HOURS:-24}"
LABEL_FILTER="${LABEL_FILTER:-docker-mcp=true}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/prune_mcp_sandboxes.sh [--apply] [--include-running]

Behavior:
  - By default this is a dry run.
  - It only targets containers with label docker-mcp=true.
  - It always considers exited/dead containers safe to remove.
  - Running containers are only considered when --include-running is set.
  - Even with --include-running, a running container must be older than
    MAX_RUNNING_AGE_HOURS (default: 24) to qualify.

Examples:
  bash scripts/prune_mcp_sandboxes.sh
  bash scripts/prune_mcp_sandboxes.sh --apply
  MAX_RUNNING_AGE_HOURS=72 bash scripts/prune_mcp_sandboxes.sh --include-running
EOF
}

section() {
  printf '\n== %s ==\n' "$1"
}

require_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    printf 'FAIL missing required command: %s\n' "${cmd}" >&2
    exit 2
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --apply)
        APPLY=1
        ;;
      --include-running)
        INCLUDE_RUNNING=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        printf 'Unknown argument: %s\n\n' "$1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
}

container_names() {
  docker ps -a \
    --filter "label=${LABEL_FILTER}" \
    --format '{{.Names}}' | awk 'NF > 0'
}

container_field() {
  local name="$1"
  local format="$2"
  docker inspect "${name}" --format "${format}"
}

container_age_hours() {
  local created_at="$1"
  python3 - "$created_at" <<'PY'
from datetime import datetime, timezone
import sys

created_raw = sys.argv[1]
created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
hours = (now - created).total_seconds() / 3600
print(f"{hours:.2f}")
PY
}

should_remove() {
  local status="$1"
  local age_hours="$2"

  case "${status}" in
    exited|dead|created)
      return 0
      ;;
    running)
      if [[ "${INCLUDE_RUNNING}" -eq 1 ]] && awk -v age="${age_hours}" -v limit="${MAX_RUNNING_AGE_HOURS}" 'BEGIN { exit !(age >= limit) }'; then
        return 0
      fi
      return 1
      ;;
    *)
      return 1
      ;;
  esac
}

main() {
  local names name status created_at age_hours image cmd target_count=0
  local -a targets=()

  require_command docker
  require_command python3
  parse_args "$@"

  section "mcp sandbox scan"
  mapfile -t names < <(container_names)

  if [[ "${#names[@]}" -eq 0 ]]; then
    printf 'OK   no docker-mcp containers found\n'
    exit 0
  fi

  for name in "${names[@]}"; do
    status="$(container_field "${name}" '{{.State.Status}}')"
    created_at="$(container_field "${name}" '{{.Created}}')"
    image="$(container_field "${name}" '{{.Config.Image}}')"
    cmd="$(container_field "${name}" '{{json .Config.Cmd}}')"
    age_hours="$(container_age_hours "${created_at}")"

    if should_remove "${status}" "${age_hours}"; then
      printf 'CANDIDATE %s status=%s age_hours=%s image=%s cmd=%s\n' "${name}" "${status}" "${age_hours}" "${image}" "${cmd}"
      targets+=("${name}")
      target_count=$((target_count + 1))
    else
      printf 'KEEP      %s status=%s age_hours=%s image=%s\n' "${name}" "${status}" "${age_hours}" "${image}"
    fi
  done

  section "summary"
  if [[ "${target_count}" -eq 0 ]]; then
    printf 'OK   no MCP sandbox containers qualify for pruning\n'
    exit 0
  fi

  if [[ "${APPLY}" -eq 0 ]]; then
    printf 'WARN dry-run only; %s candidate(s) would be removed\n' "${target_count}"
    printf 'Run with --apply to remove them.\n'
    exit 1
  fi

  printf 'Removing %s candidate(s)...\n' "${target_count}"
  docker rm -f "${targets[@]}"
  printf 'OK   removed %s MCP sandbox container(s)\n' "${target_count}"
}

main "$@"
