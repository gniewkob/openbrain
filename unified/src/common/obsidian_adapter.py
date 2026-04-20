"""
Shared Obsidian CLI adapter for local vault access and one-way sync into OpenBrain.
Used by both the main unified service and MCP gateway.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..schemas import MemoryWriteRecord


def _load_config_getter():
    """
    Import get_config in both package layouts:
    - unified package context: from ..config import get_config
    - gateway fallback context: from config import get_config
    """
    try:
        from ..config import get_config  # type: ignore[import-not-found]

        return get_config
    except ImportError:
        from config import get_config  # type: ignore[import-not-found]

        return get_config


def _load_schema_types():
    """
    Import schema types in both package layouts:
    - unified package context: from ..schemas import ...
    - gateway fallback context: from schemas import ...
    """
    try:
        from ..schemas import MemoryWriteRecord, SourceMetadata  # type: ignore[import-not-found]

        return MemoryWriteRecord, SourceMetadata
    except ImportError:
        from schemas import MemoryWriteRecord, SourceMetadata  # type: ignore[import-not-found]

        return MemoryWriteRecord, SourceMetadata


# Vault path configuration from environment
# Format: OBSIDIAN_VAULT_{VAULT_NAME}_PATH or OBSIDIAN_VAULT_PATHS as JSON
_VAULT_PATHS_CACHE: dict[str, str] = {}
_VAULT_PATHS_LOCK = asyncio.Lock()

_LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} ")
_INSTALLER_WARNING = "Your Obsidian installer is out of date."
_VALID_DOMAINS = {"corporate", "build", "personal"}


class ObsidianCliError(RuntimeError):
    """Raised when the Obsidian CLI invocation fails."""


@dataclass(slots=True)
class ObsidianNote:
    vault: str
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any]
    tags: list[str]
    file_hash: str


def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _configured_vault_names_from_env() -> list[str]:
    """Best-effort discovery of vault names from env configuration."""
    names: set[str] = set()

    paths_raw = os.environ.get("OBSIDIAN_VAULT_PATHS")
    if paths_raw:
        parsed = _parse_vault_paths_mapping(paths_raw)
        names.update(str(k).strip() for k in parsed.keys() if str(k).strip())

    prefix = "OBSIDIAN_VAULT_"
    suffix = "_PATH"
    for key in os.environ:
        if not (key.startswith(prefix) and key.endswith(suffix)):
            continue
        raw_name = key[len(prefix) : -len(suffix)].strip()
        if not raw_name:
            continue
        # OBSIDIAN_VAULT_FOO_BAR_PATH -> "FOO BAR"
        names.add(raw_name.replace("_", " "))

    return sorted(names)


def _parse_vault_paths_mapping(raw: str) -> dict[str, str]:
    """Parse OBSIDIAN_VAULT_PATHS from JSON or legacy `name:path,name:path` format."""
    text = raw.strip()
    if not text:
        return {}

    # Preferred format: JSON object
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return {
            str(k).strip(): str(v).strip()
            for k, v in parsed.items()
            if str(k).strip() and str(v).strip()
        }

    # Legacy format: "Name:/path,Other:/path2" (optionally wrapped in braces)
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()

    result: dict[str, str] = {}
    for item in text.split(","):
        pair = item.strip()
        if not pair or ":" not in pair:
            continue
        name, path = pair.split(":", 1)
        name = name.strip().strip("'\"")
        path = path.strip().strip("'\"")
        if name and path:
            result[name] = path
    return result


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
            metadata.setdefault(current_list_key, []).append(
                stripped.lstrip()[2:].strip().strip("'\"")
            )
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


def _merge_tags(frontmatter: dict[str, Any], cli_tags: list[str]) -> list[str]:
    tags: list[str] = []
    fm_tags = frontmatter.get("tags")
    if isinstance(fm_tags, str):
        tags.extend(
            [part.strip().lstrip("#") for part in fm_tags.split(",") if part.strip()]
        )
    elif isinstance(fm_tags, list):
        tags.extend(
            [str(item).strip().lstrip("#") for item in fm_tags if str(item).strip()]
        )
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


def note_to_write_payload(
    note: ObsidianNote,
    default_domain: str,
    default_entity_type: str,
    default_owner: str = "",
    default_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Convert ObsidianNote to a write payload dict for API compatibility."""
    frontmatter = note.frontmatter
    domain = str(frontmatter.get("domain") or default_domain)
    if domain not in _VALID_DOMAINS:
        domain = default_domain
    entity_type = str(
        frontmatter.get("entity_type") or frontmatter.get("type") or default_entity_type
    )
    owner = str(frontmatter.get("owner") or default_owner)
    tags = list(default_tags or [])
    tags.extend(note.tags)
    deduped_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            deduped_tags.append(tag)
    return {
        "match_key": f"obsidian:{note.vault}:{note.path}",
        "domain": domain,
        "entity_type": entity_type,
        "title": note.title,
        "content": note.content,
        "owner": owner,
        "tags": deduped_tags,
        "obsidian_ref": note.path,
        "source": {"type": "sync", "system": "obsidian", "reference": note.path},
        "sensitivity": "internal",
    }


def note_to_memory_write_record(
    note: ObsidianNote,
    default_domain: str,
    default_entity_type: str,
    default_owner: str = "",
    default_tags: list[str] | None = None,
) -> "MemoryWriteRecord":
    """Convert ObsidianNote to MemoryWriteRecord for direct use."""
    MemoryWriteRecord, SourceMetadata = _load_schema_types()

    frontmatter = note.frontmatter
    domain = str(frontmatter.get("domain") or default_domain)
    if domain not in _VALID_DOMAINS:
        domain = default_domain
    entity_type = str(
        frontmatter.get("entity_type") or frontmatter.get("type") or default_entity_type
    )
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
        domain=domain,  # type: ignore[arg-type]
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
        if command:
            self.command = command
        else:
            get_config = _load_config_getter()
            config = get_config()
            self.command = config.obsidian.cli_command
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
                "Configure OBSIDIAN_CLI_COMMAND or run this integration on a host "
                "with Obsidian installed."
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_s
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise ObsidianCliError(
                f"Obsidian CLI timed out after {self.timeout_s:.0f}s"
            ) from exc

        cleaned_stdout = _clean_cli_output(stdout.decode("utf-8", errors="replace"))
        cleaned_stderr = _clean_cli_output(stderr.decode("utf-8", errors="replace"))
        if proc.returncode != 0:
            detail = cleaned_stderr or cleaned_stdout or f"exit code {proc.returncode}"
            raise ObsidianCliError(detail)
        return cleaned_stdout

    async def list_vaults(self) -> list[str]:
        """
        List all available Obsidian vaults.

        Returns:
            List of vault names
        """
        configured = _configured_vault_names_from_env()
        try:
            raw = await self._run("vaults")
            cli_names = [line.strip() for line in raw.splitlines() if line.strip()]
            return sorted(set(cli_names) | set(configured))
        except ObsidianCliError:
            if configured:
                return configured
            raise

    @staticmethod
    def _validate_vault_path(vault: str, path: str | None = None) -> None:
        """Reject path-traversal attempts before they reach the CLI."""
        if ".." in vault.split("/") or "/" in vault or "\\" in vault:
            raise ObsidianCliError(f"Invalid vault name: {vault!r}")
        if path is not None:
            parts = PurePosixPath(path).parts
            if ".." in parts or (parts and parts[0] == "/"):
                raise ObsidianCliError(f"Invalid note path: {path!r}")

    async def list_files(
        self, vault: str, folder: str | None = None, limit: int | None = None
    ) -> list[str]:
        """
        List markdown files in a vault.
        Tries direct filesystem listing first, falls back to CLI.
        """
        self._validate_vault_path(vault, folder)

        # Try direct filesystem access
        vault_root = await self._get_vault_path(vault)
        if vault_root:
            base_path = Path(vault_root)
            if folder:
                base_path = base_path / folder

            if base_path.exists() and base_path.is_dir():
                try:
                    # Recursive search for .md files
                    paths = []
                    for p in base_path.rglob("*.md"):
                        if p.is_file():
                            # Return path relative to vault root
                            rel_path = p.relative_to(Path(vault_root))
                            paths.append(str(rel_path))
                            if limit and len(paths) >= limit:
                                break
                    return paths
                except Exception:
                    # Fallback to CLI on error
                    pass

        # CLI Fallback
        args = ["files", "ext=md", f"vault={vault}"]
        if folder:
            args.append(f"folder={folder}")
        raw = await self._run(*args)
        paths = [line.strip() for line in raw.splitlines() if line.strip()]
        if limit is not None:
            return paths[:limit]
        return paths

    async def read_note(self, vault: str, path: str) -> ObsidianNote:
        """
        Read a note from Obsidian.
        Tries direct filesystem access first, falls back to CLI.
        """
        self._validate_vault_path(vault, path)

        # Try direct filesystem access
        vault_root = await self._get_vault_path(vault)
        if vault_root:
            full_path = Path(vault_root) / path
            if full_path.exists() and full_path.is_file():
                try:
                    import aiofiles  # type: ignore[import-untyped]

                    async with aiofiles.open(
                        full_path, mode="r", encoding="utf-8"
                    ) as f:
                        raw_content = await f.read()

                    frontmatter, body = _parse_frontmatter(raw_content)
                    # For direct read, we only get tags from frontmatter
                    # Inline tags (#tag) are not parsed yet without CLI
                    tags = _merge_tags(frontmatter, [])
                    title = _derive_title(path, frontmatter, body)

                    return ObsidianNote(
                        vault=vault,
                        path=path,
                        title=title,
                        content=raw_content,
                        frontmatter=frontmatter,
                        tags=tags,
                        file_hash=_compute_hash(raw_content),
                    )
                except ImportError:  # pragma: no cover
                    raw_content = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: full_path.read_text(encoding="utf-8"),
                    )

                    frontmatter, body = _parse_frontmatter(raw_content)
                    tags = _merge_tags(frontmatter, [])
                    title = _derive_title(path, frontmatter, body)

                    return ObsidianNote(
                        vault=vault,
                        path=path,
                        title=title,
                        content=raw_content,
                        frontmatter=frontmatter,
                        tags=tags,
                        file_hash=_compute_hash(raw_content),
                    )
                except Exception:
                    # Fallback to CLI on error
                    pass

        # CLI Fallback
        content = await self._run("read", f"path={path}", f"vault={vault}")
        tags_raw = await self._run(
            "tags", f"path={path}", "format=json", f"vault={vault}"
        )
        frontmatter, body = _parse_frontmatter(content)
        cli_tags: list[str] = []
        if tags_raw:
            try:
                parsed = json.loads(tags_raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                cli_tags = [
                    str(item).strip().lstrip("#")
                    for item in parsed
                    if str(item).strip()
                ]
            elif isinstance(parsed, dict):
                cli_tags = [
                    str(key).strip().lstrip("#")
                    for key in parsed.keys()
                    if str(key).strip()
                ]
            else:
                cli_tags = [
                    line.strip().strip('"').lstrip("#")
                    for line in tags_raw.splitlines()
                    if line.strip()
                ]

        tags = _merge_tags(frontmatter, cli_tags)
        title = _derive_title(path, frontmatter, body)
        return ObsidianNote(
            vault=vault,
            path=path,
            title=title,
            content=content,
            frontmatter=frontmatter,
            tags=tags,
            file_hash=_compute_hash(content),
        )

    # =========================================================================
    # WRITE OPERATIONS (OpenBrain → Obsidian)
    # =========================================================================

    async def write_note(
        self,
        vault: str,
        path: str,
        content: str,
        frontmatter: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> ObsidianNote:
        """
        Write a note to Obsidian vault.

        Args:
            vault: Vault name
            path: Note path (e.g., "Projects/OpenBrain.md")
            content: Markdown content (without frontmatter)
            frontmatter: Optional YAML frontmatter dict
            overwrite: If True, overwrites existing note. If False, raises error
                if exists.

        Returns:
            ObsidianNote: Written note metadata

        Raises:
            ObsidianCliError: If note exists and overwrite=False, or if write fails
        """
        self._validate_vault_path(vault, path)

        # Check if note exists (unless overwriting)
        if not overwrite:
            try:
                await self.read_note(vault, path)
                raise ObsidianCliError(
                    f"Note already exists: {path}. Use overwrite=True to update."
                )
            except ObsidianCliError as e:
                if "already exists" in str(e):
                    raise
                # Note doesn't exist, proceed
                pass

        # Build full content with frontmatter
        full_content = _build_note_content(content, frontmatter)

        # Write to filesystem
        await self._write_note_to_filesystem(vault, path, full_content)

        # Return the written note (re-read to verify)
        return await self.read_note(vault, path)

    async def note_exists(self, vault: str, path: str) -> bool:
        """Check if a note exists in the vault."""
        self._validate_vault_path(vault, path)
        try:
            await self.read_note(vault, path)
            return True
        except ObsidianCliError:
            return False

    async def _get_vault_path(self, vault: str) -> str | None:
        """Get filesystem path for vault from environment configuration."""
        async with _VAULT_PATHS_LOCK:
            if vault in _VAULT_PATHS_CACHE:
                return _VAULT_PATHS_CACHE[vault]

            # Try individual env var: OBSIDIAN_VAULT_{VAULT_NAME}_PATH
            normalized = vault.upper().replace(" ", "_").replace("-", "_")
            env_var = f"OBSIDIAN_VAULT_{normalized}_PATH"
            path = os.environ.get(env_var)
            if path:
                _VAULT_PATHS_CACHE[vault] = path
                return path

            # Try aggregated config: OBSIDIAN_VAULT_PATHS
            paths_raw = os.environ.get("OBSIDIAN_VAULT_PATHS")
            if paths_raw:
                paths_map = _parse_vault_paths_mapping(paths_raw)
                if vault in paths_map:
                    _VAULT_PATHS_CACHE[vault] = paths_map[vault]
                    return paths_map[vault]

            return None

    async def update_note(
        self,
        vault: str,
        path: str,
        content: str | None = None,
        frontmatter: dict[str, Any] | None = None,
        append: bool = False,
    ) -> ObsidianNote:
        """
        Update an existing note in Obsidian vault.

        Args:
            vault: Vault name
            path: Note path
            content: New content (if None, keeps existing)
            frontmatter: New frontmatter (if None, keeps existing)
            append: If True, append content instead of replacing

        Returns:
            ObsidianNote: Updated note metadata
        """
        self._validate_vault_path(vault, path)

        # Read existing note
        existing = await self.read_note(vault, path)

        # Determine new content
        if content is None:
            new_content = existing.content
        elif append:
            new_content = existing.content + "\n\n" + content
        else:
            new_content = content

        # Determine new frontmatter
        if frontmatter is None:
            new_frontmatter = existing.frontmatter
        else:
            # Merge with existing, new values take precedence
            new_frontmatter = {**existing.frontmatter, **frontmatter}
            new_frontmatter["updated_at"] = datetime.now().isoformat()
            new_frontmatter["updated_by"] = "openbrain-sync"

        # Write updated content
        full_content = _build_note_content(new_content, new_frontmatter)
        await self._write_note_to_filesystem(vault, path, full_content)

        # Return updated note
        return await self.read_note(vault, path)

    async def delete_note(
        self,
        vault: str,
        path: str,
        backup: bool = True,
    ) -> bool:
        """
        Delete a note from Obsidian vault.

        Args:
            vault: Vault name
            path: Note path
            backup: If True, move to .trash instead of permanent deletion

        Returns:
            True if deleted, False otherwise
        """
        self._validate_vault_path(vault, path)

        vault_root = await self._get_vault_path(vault)
        if not vault_root:
            raise ObsidianCliError(f"Cannot determine path for vault: {vault}")

        full_path = Path(vault_root) / path

        if not full_path.exists():
            return False

        try:
            if backup:
                # Move to .trash folder
                trash_path = Path(vault_root) / ".trash" / path
                trash_path.parent.mkdir(parents=True, exist_ok=True)

                # Add timestamp to avoid conflicts
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                trash_path = trash_path.with_suffix(f".trash_{timestamp}.md")

                import shutil

                shutil.move(str(full_path), str(trash_path))
            else:
                # Permanent deletion
                full_path.unlink()

            return True
        except Exception as e:
            raise ObsidianCliError(f"Failed to delete note: {e}") from e

    async def _write_note_to_filesystem(
        self,
        vault: str,
        path: str,
        content: str,
    ) -> None:
        """
        Write note directly to vault filesystem.
        Uses aiofiles for async file operations.
        """
        vault_root = await self._get_vault_path(vault)
        if not vault_root:
            normalized_vault = vault.upper().replace(" ", "_").replace("-", "_")
            vault_env_key = f"OBSIDIAN_VAULT_{normalized_vault}_PATH"
            raise ObsidianCliError(
                f"Cannot determine filesystem path for vault: {vault}. "
                f"Set {vault_env_key} or "
                f"OBSIDIAN_VAULT_PATHS environment variable."
            )

        # Validate vault path exists
        vault_path = Path(vault_root)
        if not vault_path.exists():
            raise ObsidianCliError(f"Vault path does not exist: {vault_root}")
        if not vault_path.is_dir():
            raise ObsidianCliError(f"Vault path is not a directory: {vault_root}")

        # Build full path and validate it's within vault.
        # resolve() follows symlinks — prevents traversal via symlinked dirs.
        full_path = (vault_path / path).resolve()
        vault_resolved = vault_path.resolve()
        try:
            full_path.relative_to(vault_resolved)
        except ValueError:
            raise ObsidianCliError(f"Path escapes vault directory: {path}")

        # Ensure parent directories exist
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file using asyncio (non-blocking)
        # Import here to avoid dependency issues if aiofiles not installed
        try:
            import aiofiles

            async with aiofiles.open(full_path, "w", encoding="utf-8") as f:
                await f.write(content)
        except ImportError:  # pragma: no cover
            # Fallback to sync file write with thread pool
            import asyncio

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Default executor
                lambda: _sync_write_file(full_path, content),
            )


def _sync_write_file(path: Path, content: str) -> None:
    """Synchronous file write (used as fallback)."""
    path.write_text(content, encoding="utf-8")


def _build_note_content(
    content: str,
    frontmatter: dict[str, Any] | None = None,
) -> str:
    """Build full note content with YAML frontmatter."""
    if not frontmatter:
        return content

    fm_lines = ["---"]
    for key, value in frontmatter.items():
        if value is None:
            continue
        if isinstance(value, list):
            fm_lines.append(f"{key}:")
            for item in value:
                fm_lines.append(f"  - {item}")
        elif isinstance(value, bool):
            fm_lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            fm_lines.append(f"{key}: {value}")
        else:
            # Escape strings containing special characters
            str_val = str(value)
            if any(
                c in str_val
                for c in [
                    ":",
                    "#",
                    '"',
                    "'",
                    "[",
                    "]",
                    "{",
                    "}",
                    ",",
                    "&",
                    "*",
                    "?",
                    "|",
                    "-",
                    "<",
                    ">",
                    "=",
                    "!",
                    "%",
                    "@",
                    "`",
                ]
            ):
                str_val = f'"{str_val.replace("\\", "\\\\").replace('"', '\\"')}"'
            fm_lines.append(f"{key}: {str_val}")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(content)

    return "\n".join(fm_lines)
