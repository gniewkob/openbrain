#!/usr/bin/env python3
"""Generate operational dashboard note for OpenBrain + Obsidian.

Data sources:
- OpenBrain backend (readyz + memory/find)
- Maintenance logs (weekly_maintain_dry_run.log, frontmatter_cleanup.log)
- Obsidian vault filesystem counters

Output:
- Obsidian note: 90 System/OpenBrain Obsidian Dashboard.md

Required env vars:
- OBSIDIAN_VAULT_ROOT (or OBSIDIAN_PERSONAL_VAULT): path to personal Obsidian vault
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import error, request

from _config import LOG_DIR, Conn, load_conn, vault_root

WEEKLY_LOG = LOG_DIR / "weekly_maintain_dry_run.log"
CLEANUP_LOG = LOG_DIR / "frontmatter_cleanup.log"

PAT_DIRTY_TAG = re.compile(r"^\{'tag':\s*'(#?[^']+)'\}$")
_MACHINE_KEY_RE = re.compile(
    r"^(openbrain_id|domain|entity_type|status|sensitivity)\s*:",
    re.MULTILINE,
)


def http_json(
    conn: Conn,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    retries: int = 4,
) -> Any:
    body = None
    headers = {"X-Internal-Key": conn.api_key}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_exc: Exception | None = None
    for i in range(retries):
        try:
            req = request.Request(
                f"{conn.base_url}{path}", data=body, method=method, headers=headers
            )
            with request.urlopen(req, timeout=60) as resp:
                txt = resp.read().decode("utf-8")
                return json.loads(txt) if txt else {}
        except error.HTTPError as exc:
            msg = exc.read().decode("utf-8", "ignore")
            raise RuntimeError(f"HTTP {exc.code} {path}: {msg[:300]}") from exc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.5 * (i + 1))
    if last_exc:
        raise last_exc
    raise RuntimeError("Unexpected HTTP failure")


def safe_readyz(conn: Conn) -> tuple[str, dict[str, Any]]:
    try:
        data = http_json(conn, "GET", "/readyz")
        status = "ok" if data.get("status") == "ok" else "degraded"
        return status, data
    except Exception:  # noqa: BLE001
        return "down", {}


def fetch_records(conn: Conn, status: str, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = http_json(
            conn,
            "POST",
            "/api/v1/memory/find",
            {
                "query": None,
                "filters": {"status": status},
                "limit": limit,
                "offset": offset,
                "sort": "updated_at_desc",
            },
        )
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        offset += limit
        if offset > 10000:
            break
    return [p.get("record", p) for p in out]


def looks_like_frontmatter_content(content: str) -> bool:
    if not content.startswith("---\n"):
        return False
    end = content.find("\n---\n", 4)
    if end == -1:
        return False
    fm = content[4:end]
    return bool(_MACHINE_KEY_RE.search(fm))


def parse_json_lines(path: Path, max_items: int = 20) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        # either pure json line or timestamp + json blob
        start = line.find("{")
        if start == -1:
            continue
        prefix = line[:start].strip()
        raw = line[start:]
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                if prefix and "timestamp" not in obj:
                    obj["timestamp"] = prefix
                items.append(obj)
        except Exception:  # noqa: BLE001
            continue
    return items[-max_items:]


def count_markdown_files(root: Path) -> int:
    return sum(1 for _ in root.rglob("*.md"))


def glob_count(directory: Path) -> int:
    """Count .md files in directory; returns 0 if directory does not exist."""
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob("*.md"))


def top_entities(records: list[dict[str, Any]], n: int = 8) -> list[tuple[str, int]]:
    c = Counter((r.get("entity_type") or "unknown") for r in records)
    return c.most_common(n)


def mk_table(headers: list[str], rows: list[list[str]]) -> str:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def render_dashboard(
    *,
    now_iso: str,
    ready_state: str,
    ready_data: dict[str, Any],
    active_records: list[dict[str, Any]],
    superseded_records: list[dict[str, Any]],
    weekly_runs: list[dict[str, Any]],
    cleanup_runs: list[dict[str, Any]],
    vault: Path,
) -> str:
    active_by_domain = Counter((r.get("domain") or "unknown") for r in active_records)
    dirty_tag_records = 0
    fm_like_records = 0
    for r in active_records:
        tags = r.get("tags") or []
        if any(isinstance(t, str) and PAT_DIRTY_TAG.match(t) for t in tags):
            dirty_tag_records += 1
        content = r.get("content") or ""
        if isinstance(content, str) and looks_like_frontmatter_content(content):
            fm_like_records += 1

    proposals_count = glob_count(vault / "00 Inbox/AI Proposals")
    suggestions_count = glob_count(vault / "90 System/AI Suggestions")
    total_notes = count_markdown_files(vault)

    entity_rows = [[k, str(v)] for k, v in top_entities(active_records)]

    weekly_rows: list[list[str]] = []
    for run in weekly_runs[-8:]:
        ts = str(run.get("timestamp", "-"))
        mode = run.get("mode")
        if mode is None and "dry_run" in run:
            mode = "dry_run" if bool(run.get("dry_run")) else "apply"
        weekly_rows.append(
            [
                ts[:19],
                str(mode if mode is not None else "-"),
                str(run.get("total_scanned", "-")),
                str(run.get("dedup_found", "-")),
                str(run.get("owners_normalized", "-")),
                str(run.get("links_fixed", "-")),
            ]
        )

    cleanup_rows: list[list[str]] = []
    for run in cleanup_runs[-8:]:
        cleanup_rows.append(
            [
                str(run.get("timestamp", "-"))[:19],
                str(run.get("mode", "-")),
                str(run.get("frontmatter_candidates", "-")),
                str(run.get("applied", "-")),
                str(run.get("failed", "-")),
            ]
        )

    mermaid_pie_lines = ["```mermaid", "pie title Active Memories by Domain"]
    for domain, count in active_by_domain.items():
        mermaid_pie_lines.append(f'    "{domain}" : {count}')
    mermaid_pie_lines.append("```")
    pie_block = "\n".join(mermaid_pie_lines)

    ready_db = ready_data.get("db", "-")
    ready_vs = ready_data.get("vector_store", "-")

    lines = [
        "---",
        "type: dashboard",
        "status: active",
        f"updated: {now_iso}",
        "area: operations",
        "tags:",
        "  - openbrain",
        "  - obsidian",
        "  - dashboard",
        "  - operations",
        "---",
        "",
        "# OpenBrain + Obsidian Dashboard",
        "",
        f"Last refresh: `{now_iso}`",
        "",
        "## Service Health",
        "",
        f"- OpenBrain readyz: `{ready_state}`",
        f"- Database: `{ready_db}`",
        f"- Vector store: `{ready_vs}`",
        "",
        "## OpenBrain Snapshot",
        "",
        f"- Active memories: `{len(active_records)}`",
        f"- Superseded memories: `{len(superseded_records)}`",
        f"- Dirty-tag records (active): `{dirty_tag_records}`",
        f"- Frontmatter-like content records (active): `{fm_like_records}`",
        "",
        pie_block,
        "",
        "### Top Entity Types (active)",
        "",
        mk_table(["entity_type", "count"], entity_rows or [["-", "0"]]),
        "",
        "## Obsidian Snapshot",
        "",
        f"- Total markdown notes in vault: `{total_notes}`",
        f"- `00 Inbox/AI Proposals`: `{proposals_count}`",
        f"- `90 System/AI Suggestions`: `{suggestions_count}`",
        "",
        "## Weekly Maintenance (from logs)",
        "",
        mk_table(
            [
                "timestamp",
                "mode",
                "scanned",
                "dedup_found",
                "owners_norm",
                "links_fixed",
            ],
            weekly_rows or [["-", "-", "-", "-", "-", "-"]],
        ),
        "",
        "## Frontmatter Cleanup Runs (from logs)",
        "",
        mk_table(
            ["timestamp", "mode", "candidates", "applied", "failed"],
            cleanup_rows or [["-", "-", "-", "-", "-"]],
        ),
        "",
        "## Thresholds",
        "",
        "- `dirty-tag records > 0` -> run tag cleanup stage",
        "- `frontmatter-like records > 0` -> run frontmatter cleanup stage",
        "- `dedup_found > 0` in weekly dry-run -> review and execute maintenance",
        "- `service health != ok` -> check `start_unified.sh status` and container logs",
        "",
        "## Optional Grafana",
        "",
        "- URL: `http://localhost:3005`",
        "- Use for longer trend windows (latency, backend health, maintenance frequency)",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    conn = load_conn()
    vault = vault_root()
    dashboard_path = vault / "90 System/OpenBrain Obsidian Dashboard.md"
    now_iso = time.strftime("%Y-%m-%d %H:%M:%S %z")

    ready_state, ready_data = safe_readyz(conn)
    active_records = fetch_records(conn, "active") if ready_state != "down" else []
    superseded_records = (
        fetch_records(conn, "superseded") if ready_state != "down" else []
    )

    weekly_runs = parse_json_lines(WEEKLY_LOG, max_items=30)
    cleanup_runs = parse_json_lines(CLEANUP_LOG, max_items=30)

    dashboard = render_dashboard(
        now_iso=now_iso,
        ready_state=ready_state,
        ready_data=ready_data,
        active_records=active_records,
        superseded_records=superseded_records,
        weekly_runs=weekly_runs,
        cleanup_runs=cleanup_runs,
        vault=vault,
    )

    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(dashboard, encoding="utf-8")
    print(str(dashboard_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
