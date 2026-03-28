"""
Obsidian CLI adapter for local vault access and one-way sync into OpenBrain.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .schemas import MemoryWriteRecord


_LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} ")
_INSTALLER_WARNING = "Your Obsidian installer is out of date."
_VALID_DOMAINS = {"corporate", "build", "personal"}


def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ObsidianCliError(RuntimeError):
    """Raised when the Obsidian CLI invocation fails."""


@dataclass(slots=True)
class ObsidianNote:
    vault: str
    path: str
    content: str
    frontmatter: dict[str, Any]
    tags: list[str]
    title: str
    file_hash: str


def _clean_cli_output(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if _LOG_PREFIX_RE.match(stripped) and "Loading updated app package" in stripped:
            continue
        if stripped.startswith(_INSTALLER_WARNING):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _coerce_frontmatter_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    return value


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, content

    metadata: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in lines[1:end_idx]:
        stripped = line.rstrip()
        if not stripped:
            continue
        if stripped.lstrip().startswith("- ") and current_list_key:
            metadata.setdefault(current_list_key, []).append(stripped.lstrip()[2:].strip().strip("'\""))
            continue
        if ":" not in stripped:
            current_list_key = None
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            metadata[key] = _coerce_frontmatter_value(raw_value)
            current_list_key = None
        else:
            metadata[key] = []
            current_list_key = key

    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return metadata, body


def _coerce_tags(frontmatter: dict[str, Any], cli_tags: list[str]) -> list[str]:
    tags: list[str] = []
    fm_tags = frontmatter.get("tags")
    if isinstance(fm_tags, str):
        tags.extend([part.strip().lstrip("#") for part in fm_tags.split(",") if part.strip()])
    elif isinstance(fm_tags, list):
        tags.extend([str(item).strip().lstrip("#") for item in fm_tags if str(item).strip()])
    tags.extend(tag.lstrip("#") for tag in cli_tags if tag)
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _derive_title(path: str, frontmatter: dict[str, Any], body: str) -> str:
    title = frontmatter.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return PurePosixPath(path).stem


def note_to_memory_write_record(
    note: ObsidianNote,
    default_domain: str,
    default_entity_type: str,
    default_owner: str = "",
    default_tags: list[str] | None = None,
) -> "MemoryWriteRecord":
    from .schemas import MemoryWriteRecord, SourceMetadata

    frontmatter = note.frontmatter
    domain = str(frontmatter.get("domain") or default_domain)
    if domain not in _VALID_DOMAINS:
        domain = default_domain
    entity_type = str(frontmatter.get("entity_type") or frontmatter.get("type") or default_entity_type)
    owner = str(frontmatter.get("owner") or default_owner)
    tags = list(default_tags or [])
    tags.extend(note.tags)
    deduped_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            deduped_tags.append(tag)

    return MemoryWriteRecord(
        match_key=f"obsidian:{note.vault}:{note.path}",
        domain=domain,
        entity_type=entity_type,
        title=note.title,
        content=note.content,
        owner=owner,
        tags=deduped_tags,
        source=SourceMetadata(type="sync", system="obsidian", reference=note.path),
        obsidian_ref=note.path,
    )


class ObsidianCliAdapter:
    def __init__(self, command: str | None = None, timeout_s: float = 30.0) -> None:
        self.command = command or os.environ.get("OBSIDIAN_CLI_COMMAND", "obsidian")
        self.timeout_s = timeout_s

    async def _run(self, *args: str) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ObsidianCliError(
                f"Obsidian CLI command not found: {self.command}. "
                "Configure OBSIDIAN_CLI_COMMAND or run this integration on a host with Obsidian installed."
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise ObsidianCliError(f"Obsidian CLI timed out after {self.timeout_s:.0f}s") from exc

        cleaned_stdout = _clean_cli_output(stdout.decode("utf-8", errors="replace"))
        cleaned_stderr = _clean_cli_output(stderr.decode("utf-8", errors="replace"))
        if proc.returncode != 0:
            detail = cleaned_stderr or cleaned_stdout or f"exit code {proc.returncode}"
            raise ObsidianCliError(detail)
        return cleaned_stdout

    async def list_vaults(self) -> list[str]:
        raw = await self._run("vaults")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    async def list_files(self, vault: str, folder: str | None = None, limit: int | None = None) -> list[str]:
        args = ["files", "ext=md", f"vault={vault}"]
        if folder:
            args.append(f"folder={folder}")
        raw = await self._run(*args)
        paths = [line.strip() for line in raw.splitlines() if line.strip()]
        if limit is not None:
            return paths[:limit]
        return paths

    async def read_note(self, vault: str, path: str) -> ObsidianNote:
        content = await self._run("read", f"path={path}", f"vault={vault}")
        tags_raw = await self._run("tags", f"path={path}", "format=json", f"vault={vault}")
        frontmatter, body = _parse_frontmatter(content)
        cli_tags: list[str] = []
        if tags_raw:
            try:
                parsed = json.loads(tags_raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                cli_tags = [str(item).strip().lstrip("#") for item in parsed if str(item).strip()]
            elif isinstance(parsed, dict):
                cli_tags = [str(key).strip().lstrip("#") for key in parsed.keys() if str(key).strip()]
            else:
                cli_tags = [line.strip().strip('"').lstrip("#") for line in tags_raw.splitlines() if line.strip()]
        tags = _coerce_tags(frontmatter, cli_tags)
        title = _derive_title(path, frontmatter, body)
        return ObsidianNote(
            vault=vault,
            path=path,
            content=content,
            frontmatter=frontmatter,
            tags=tags,
            title=title,
            file_hash=_compute_hash(content),
        )
