#!/usr/bin/env python3
"""Clean duplicated Obsidian frontmatter from OpenBrain memory content.

Scope:
- records with obsidian_ref
- content starting with YAML frontmatter block
- frontmatter contains machine metadata keys (openbrain_id/domain/entity_type/status/sensitivity)

Default mode is dry-run. Use --apply to persist updates.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from _config import LOG_DIR, Conn, load_conn

LOG_PATH = LOG_DIR / "frontmatter_cleanup.log"

# Match machine-generated YAML keys at the start of a frontmatter line.
# Uses line-start anchoring (re.MULTILINE) to avoid false-positives where
# e.g. "status:" appears mid-sentence in real content.
_MACHINE_KEY_RE = re.compile(
    r"^(openbrain_id|domain|entity_type|status|sensitivity)\s*:",
    re.MULTILINE,
)


@dataclass
class Candidate:
    memory_id: str
    domain: str
    obsidian_ref: str
    old_content: str
    new_content: str


def http_json(
    *,
    conn: Conn,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    retries: int = 4,
) -> dict[str, Any] | list[Any]:
    body = None
    headers = {"X-Internal-Key": conn.api_key}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_exc: Exception | None = None
    for i in range(retries):
        try:
            req = request.Request(
                f"{conn.base_url}{path}",
                data=body,
                method=method,
                headers=headers,
            )
            with request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            msg = exc.read().decode("utf-8", "ignore")
            raise RuntimeError(f"HTTP {exc.code} {path}: {msg[:300]}") from exc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.5 * (i + 1))
    if last_exc:
        raise last_exc
    raise RuntimeError("Unexpected HTTP failure")


def list_active_records(conn: Conn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = http_json(
            conn=conn,
            method="POST",
            path="/api/v1/memory/find",
            payload={
                "query": None,
                "filters": {"status": "active"},
                "limit": 50,
                "offset": offset,
                "sort": "updated_at_desc",
            },
        )
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        offset += 50
        if offset > 10000:
            break
    return out


def extract_frontmatter(content: str) -> tuple[str, str] | None:
    if not content.startswith("---\n"):
        return None
    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return None
    fm = content[4:end_idx]
    body = content[end_idx + 5 :]
    return fm, body


def build_candidates(records: list[dict[str, Any]]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for hit in records:
        rec = hit.get("record", hit)
        obsidian_ref = rec.get("obsidian_ref")
        if not isinstance(obsidian_ref, str) or not obsidian_ref.strip():
            continue

        content = rec.get("content") or ""
        if not isinstance(content, str):
            continue

        parsed = extract_frontmatter(content)
        if parsed is None:
            continue
        fm, body = parsed

        # Strip only when frontmatter clearly looks like transport metadata.
        if not _MACHINE_KEY_RE.search(fm):
            continue

        new_content = body.lstrip("\n")
        if new_content == content:
            continue

        candidates.append(
            Candidate(
                memory_id=rec["id"],
                domain=rec.get("domain", ""),
                obsidian_ref=obsidian_ref,
                old_content=content,
                new_content=new_content,
            )
        )
    return candidates


def apply_updates(conn: Conn, candidates: list[Candidate]) -> tuple[int, list[str]]:
    applied = 0
    failed: list[str] = []
    for c in candidates:
        try:
            http_json(
                conn=conn,
                method="PATCH",
                path=f"/api/v1/memory/{c.memory_id}",
                payload={
                    "content": c.new_content,
                    "updated_by": "agent",
                },
            )
            applied += 1
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{c.memory_id}: {exc}")
    return applied, failed


def append_log(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    args = parser.parse_args()

    conn = load_conn()
    records = list_active_records(conn)
    candidates = build_candidates(records)

    by_domain: dict[str, int] = {}
    for c in candidates:
        by_domain[c.domain] = by_domain.get(c.domain, 0) + 1

    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = {
        "timestamp": ts,
        "mode": "apply" if args.apply else "dry_run",
        "active_records": len(records),
        "frontmatter_candidates": len(candidates),
        "by_domain": by_domain,
    }

    if args.apply:
        applied, failed = apply_updates(conn, candidates)
        summary["applied"] = applied
        summary["failed"] = len(failed)
        if failed:
            summary["failed_examples"] = failed[:10]

    print(json.dumps(summary, ensure_ascii=True))
    append_log(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
