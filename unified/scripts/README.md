# Maintenance scripts

Helper scripts for OpenBrain operations. Each tool is safe to run repeatedly
and most default to **dry-run** mode — read the per-script docstring for
exact flags.

All scripts share configuration via `_config.py`, which resolves:

| Source | Var | Default |
|---|---|---|
| `OPENBRAIN_CONFIG` | path to `.mcp.json` containing `BRAIN_URL` + `INTERNAL_API_KEY` | `<repo-root>/.mcp.json` |
| `OPENBRAIN_LOG_DIR` | log output directory | `<repo-root>/unified/logs` |
| `OBSIDIAN_VAULT_ROOT` or `OBSIDIAN_PERSONAL_VAULT` | personal vault path | (auto-detected) |

`<repo-root>` is derived from this file's location (`scripts/ → unified/ → openbrain/`).

---

## `_config.py`

Shared helper module — not invoked directly. Imported by every other Python
script in this folder.

Exposes:
- `LOG_DIR: Path`
- `CONFIG_PATH: Path`
- `Conn(base_url, api_key)` dataclass + `load_conn()` factory
- `vault_root()` for Obsidian filesystem access

---

## `cleanup_frontmatter_content.py`

Removes duplicated Obsidian frontmatter from OpenBrain memory `content` fields
(where the same YAML appears both in DB frontmatter metadata and inlined into
the body).

```bash
# Dry-run (default) — reports what would change, writes nothing
python unified/scripts/cleanup_frontmatter_content.py

# Apply the changes via PATCH /api/v1/memory/{id}
python unified/scripts/cleanup_frontmatter_content.py --apply
```

Scope: only records with `obsidian_ref` whose content starts with a YAML
frontmatter block containing machine metadata (`openbrain_id`, `domain`,
`entity_type`, `status`, `sensitivity`).

Logs to `<OPENBRAIN_LOG_DIR>/frontmatter_cleanup.log`.

---

## `generate_openbrain_obsidian_dashboard.py`

Generates a Markdown operational dashboard note inside the Obsidian vault:
`90 System/OpenBrain Obsidian Dashboard.md`.

```bash
# Requires OBSIDIAN_VAULT_ROOT or OBSIDIAN_PERSONAL_VAULT to be set in .env
python unified/scripts/generate_openbrain_obsidian_dashboard.py
```

Data sources:
- OpenBrain backend (`/readyz`, `/memory/find`)
- Maintenance logs (`weekly_maintain_dry_run.log`, `frontmatter_cleanup.log`)
- Obsidian vault filesystem counters

Run on a schedule (e.g. daily cron / launchd) to keep the dashboard fresh.

---

## `obsidian_inbox_cleanup.sh`

Moves interview / system notes from the Obsidian inbox to canonical folders
and archives stragglers.

```bash
# Dry-run (default) — prints intended moves
./unified/scripts/obsidian_inbox_cleanup.sh

# Apply
./unified/scripts/obsidian_inbox_cleanup.sh --apply
```

Sources `.env` from repo root for `OBSIDIAN_PERSONAL_VAULT`.

---

## `weekly_maintenance_dry_run.sh`

Cron-friendly weekly check: runs `brain_maintain` in dry-run mode and logs
the result. Designed for `launchd` / cron without arguments.

```bash
./unified/scripts/weekly_maintenance_dry_run.sh
```

Output: `<OPENBRAIN_LOG_DIR>/weekly_maintain_dry_run.log` (append-only).

Reads `BRAIN_URL` + `INTERNAL_API_KEY` from `OPENBRAIN_CONFIG` (default
`.mcp.json` at repo root).

---

## `check_memory_paths.py`

Guardrail script (used in CI) that verifies `unified/src/memory_paths.py`
stays in sync with `unified/mcp-gateway/src/memory_paths.py`. Not for
manual operations.

---

## Scheduling

Examples for running these on a Mac via `launchd`. Adapt paths and intervals
for your environment.

- **Daily maintenance dry-run** at 02:00:
  ```xml
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
  ```
- **Daily DB backup** at 03:00: see `launchd/com.openbrain.postgres-backup.plist`
  (already committed; load with `launchctl load ~/Library/LaunchAgents/...`).

For cron equivalents on Linux, the same scripts work as-is (they don't depend
on launchd-specific env).
