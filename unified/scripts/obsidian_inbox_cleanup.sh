#!/usr/bin/env bash
set -euo pipefail

# Obsidian Inbox Cleanup
# - moves interview notes to project folder
# - moves OpenBrain docs to system folder
# - archives remaining inbox markdown files
# Usage:
#   ./unified/scripts/obsidian_inbox_cleanup.sh --dry-run
#   ./unified/scripts/obsidian_inbox_cleanup.sh --apply

MODE="dry-run"
if [[ "${1:-}" == "--apply" ]]; then
  MODE="apply"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

VAULT_ROOT="${OBSIDIAN_VAULT_ROOT:-${OBSIDIAN_PERSONAL_VAULT:-}}"
if [[ -z "$VAULT_ROOT" ]]; then
  echo "ERROR: set OBSIDIAN_VAULT_ROOT or OBSIDIAN_PERSONAL_VAULT in environment."
  exit 1
fi

INBOX_DIR="$VAULT_ROOT/00 Inbox"
INTERVIEW_DIR="$VAULT_ROOT/04 Projects/Vaillant Interview 2026-04-21"
OPENBRAIN_DIR="$VAULT_ROOT/90 System/OpenBrain"
TODAY="$(date +%F)"
ARCHIVE_DIR="$VAULT_ROOT/06 Resources/Inbox Archive/Processed $TODAY"

if [[ ! -d "$INBOX_DIR" ]]; then
  echo "ERROR: Inbox does not exist: $INBOX_DIR"
  exit 1
fi

mkdir -p "$INTERVIEW_DIR" "$OPENBRAIN_DIR" "$ARCHIVE_DIR"

log_move() {
  local src="$1"
  local dst="$2"
  if [[ "$MODE" == "dry-run" ]]; then
    echo "DRYRUN|$src|$dst"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  mv "$src" "$dst"
  echo "MOVED|$src|$dst"
}

move_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    log_move "$src" "$dst"
  fi
}

# 1) Interview set
for f in \
  "Day1_Interview_Cheat_Sheet_v2.md" \
  "Day2_Role_vs_Peers.md" \
  "Day3_Scope_PainPoints_Vision.md" \
  "Day4_Tough_Questions.md" \
  "Day5_Interview_Simulation.md" \
  "Master_QA_CheatSheet.md" \
  "Weekend_Final_CheatSheet.md" \
  "Interview_Live_System.md" \
  "Interview_Live_System_Inline_Humanized_v3_top15.md"
do
  move_if_exists "$INBOX_DIR/$f" "$INTERVIEW_DIR/$f"
done

# 2) OpenBrain docs
for f in \
  "ai_second_brain_openbrain_documentation.md" \
  "ai_second_brain_operating_model_v2.md" \
  "OpenBrain MCP Smoke Note.md"
do
  move_if_exists "$INBOX_DIR/$f" "$OPENBRAIN_DIR/$f"
done

# 3) AI Proposals subtree
if [[ -d "$INBOX_DIR/AI Proposals" ]]; then
  if [[ "$MODE" == "dry-run" ]]; then
    echo "DRYRUN_DIR|$INBOX_DIR/AI Proposals|$ARCHIVE_DIR/AI Proposals"
  else
    mkdir -p "$ARCHIVE_DIR/AI Proposals"
    find "$INBOX_DIR/AI Proposals" -mindepth 1 -maxdepth 1 -exec mv {} "$ARCHIVE_DIR/AI Proposals/" \;
    rmdir "$INBOX_DIR/AI Proposals" || true
    echo "MOVED_DIR|$INBOX_DIR/AI Proposals|$ARCHIVE_DIR/AI Proposals"
  fi
fi

# 4) Remaining markdown in 00 Inbox -> dated archive
while IFS= read -r -d '' md_file; do
  base="$(basename "$md_file")"
  log_move "$md_file" "$ARCHIVE_DIR/$base"
done < <(find "$INBOX_DIR" -maxdepth 1 -type f -name "*.md" -print0)

echo "SUMMARY|mode=$MODE|inbox=$INBOX_DIR|archive=$ARCHIVE_DIR"
