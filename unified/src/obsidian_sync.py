"""
Bi-directional Sync Engine for OpenBrain ↔ Obsidian.

Implements conflict resolution, change tracking, and bidirectional synchronization
between OpenBrain memories and Obsidian notes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Optional

from .exceptions import ObsidianCliError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .common.obsidian_adapter import ObsidianCliAdapter
    from .schemas import MemoryOut

# Imports used in helper functions
from .memory_reads import list_memories

log = logging.getLogger(__name__)


class SyncStrategy(str, Enum):
    """Conflict resolution strategies."""

    LAST_WRITE_WINS = "last_write_wins"  # Timestamp-based
    DOMAIN_BASED = "domain_based"  # Corporate=OpenBrain wins, Personal=Obsidian wins
    MANUAL_REVIEW = "manual_review"  # Flag for manual conflict resolution


class ChangeType(str, Enum):
    """Types of changes detected."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


@dataclass
class SyncState:
    """State of an item for sync tracking."""

    memory_id: str
    obsidian_path: str
    vault: str
    content_hash: str  # Hash of content for quick comparison
    memory_updated_at: datetime
    obsidian_modified_at: datetime
    last_sync_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize SyncState to a JSON-compatible dictionary."""
        return {
            "memory_id": self.memory_id,
            "obsidian_path": self.obsidian_path,
            "vault": self.vault,
            "content_hash": self.content_hash,
            "memory_updated_at": self.memory_updated_at.isoformat()
            if self.memory_updated_at
            else None,
            "obsidian_modified_at": self.obsidian_modified_at.isoformat()
            if self.obsidian_modified_at
            else None,
            "last_sync_at": self.last_sync_at.isoformat()
            if self.last_sync_at
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncState":
        """Deserialize a SyncState from a dictionary produced by to_dict."""
        return cls(
            memory_id=data["memory_id"],
            obsidian_path=data["obsidian_path"],
            vault=data["vault"],
            content_hash=data["content_hash"],
            memory_updated_at=datetime.fromisoformat(data["memory_updated_at"])
            if data.get("memory_updated_at")
            else datetime.now(timezone.utc),
            obsidian_modified_at=datetime.fromisoformat(data["obsidian_modified_at"])
            if data.get("obsidian_modified_at")
            else datetime.now(timezone.utc),
            last_sync_at=datetime.fromisoformat(data["last_sync_at"])
            if data.get("last_sync_at")
            else None,
        )


@dataclass
class SyncChange:
    """Detected change between OpenBrain and Obsidian."""

    memory_id: str
    obsidian_path: str
    vault: str
    change_type: ChangeType
    source: Literal["openbrain", "obsidian", "both"]  # Where the change originated
    openbrain_state: Optional[SyncState] = None
    obsidian_state: Optional[SyncState] = None
    conflict: bool = False
    resolution: Optional[str] = None  # How conflict was/will be resolved

    def to_dict(self) -> dict[str, Any]:
        """Serialize SyncChange to a JSON-compatible dictionary."""
        return {
            "memory_id": self.memory_id,
            "obsidian_path": self.obsidian_path,
            "vault": self.vault,
            "change_type": self.change_type.value,
            "source": self.source,
            "openbrain_state": self.openbrain_state.to_dict()
            if self.openbrain_state
            else None,
            "obsidian_state": self.obsidian_state.to_dict()
            if self.obsidian_state
            else None,
            "conflict": self.conflict,
            "resolution": self.resolution,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""

    started_at: datetime
    completed_at: Optional[datetime] = None
    changes_detected: int = 0
    changes_applied: int = 0
    conflicts: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    details: list[SyncChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize SyncResult to a JSON-compatible dictionary."""
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "changes_detected": self.changes_detected,
            "changes_applied": self.changes_applied,
            "conflicts": self.conflicts,
            "errors": self.errors,
            "details": [d.to_dict() for d in self.details],
        }


class ObsidianChangeTracker:
    """
    Tracks changes between OpenBrain and Obsidian.

    Stores sync state in a JSON file for persistence across restarts.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or self._default_storage_path()
        self._state: dict[str, SyncState] = {}  # key: "vault:obsidian_path"
        self._load_state()

    def _default_storage_path(self) -> str:
        """Default path for sync state storage."""
        import os
        from .config import get_config

        config = get_config()
        data_dir = config.obsidian.data_dir
        return os.path.join(data_dir, "obsidian_sync_state.json")

    def _load_state(self) -> None:
        """Load sync state from disk."""
        import os

        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, state_data in data.items():
                        self._state[key] = SyncState.from_dict(state_data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # If corrupted, start fresh
                log.warning("Could not load sync state: %s", e)
                self._state = {}

    def _save_state(self) -> None:
        """Save sync state to disk."""
        import os

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

        data = {key: state.to_dict() for key, state in self._state.items()}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _make_key(self, vault: str, path: str) -> str:
        """Create unique key for a vault+path combination."""
        return f"{vault}:{path}"

    def get_state(self, vault: str, path: str) -> Optional[SyncState]:
        """Get last known sync state for an item."""
        key = self._make_key(vault, path)
        return self._state.get(key)

    def update_state(self, state: SyncState) -> None:
        """Update sync state for an item."""
        key = self._make_key(state.vault, state.obsidian_path)
        state.last_sync_at = datetime.now(timezone.utc)
        self._state[key] = state
        self._save_state()

    def remove_state(self, vault: str, path: str) -> None:
        """Remove state for deleted items."""
        key = self._make_key(vault, path)
        if key in self._state:
            del self._state[key]
            self._save_state()

    def get_all_states(self) -> list[SyncState]:
        """Get all tracked states."""
        return list(self._state.values())

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about tracked items."""
        now = datetime.now(timezone.utc)

        total = len(self._state)
        never_synced = sum(1 for s in self._state.values() if s.last_sync_at is None)
        synced_recently = sum(
            1
            for s in self._state.values()
            if s.last_sync_at and (now - s.last_sync_at).days < 7
        )

        return {
            "total_tracked": total,
            "never_synced": never_synced,
            "synced_recently": synced_recently,
            "storage_path": self.storage_path,
        }


async def _get_openbrain_memories(
    session: "AsyncSession",
    vault: str,
) -> dict[str, "MemoryOut"]:
    """
    Fetch all memories from OpenBrain that have obsidian_ref.

    Args:
        session: Database session
        vault: Obsidian vault name

    Returns:
        Dictionary mapping obsidian_ref to MemoryOut
    """
    all_memories = await list_memories(session, {}, limit=1000)
    return {m.obsidian_ref: m for m in all_memories if m.obsidian_ref}


async def _get_obsidian_files(
    adapter: "ObsidianCliAdapter",
    vault: str,
) -> set[str]:
    """
    Fetch list of files from Obsidian vault.

    Args:
        adapter: Obsidian CLI adapter
        vault: Obsidian vault name

    Returns:
        Set of file paths in the vault
    """
    try:
        files = await adapter.list_files(vault, limit=1000)
        return set(files)
    except Exception as e:
        log.warning("obsidian_list_files_failed: %s (vault=%s)", str(e), vault)
        return set()


def _check_memory_changed(
    state: SyncState,
    memory: "MemoryOut | None",
    compute_hash: Any,
) -> bool:
    """
    Check if memory content has changed since last sync.

    Args:
        state: Last known sync state
        memory: Current memory from OpenBrain (None if deleted)
        compute_hash: Function to compute content hash

    Returns:
        True if memory has changed
    """
    if not memory:
        return False

    current_hash = compute_hash(memory.content)
    if current_hash != state.content_hash:
        return True

    if memory.updated_at and memory.updated_at > state.memory_updated_at:
        return True

    return False


def _create_sync_change(
    state: SyncState,
    change_type: ChangeType,
    source: Literal["openbrain", "obsidian", "both"],
    conflict: bool = False,
) -> SyncChange:
    """
    Create a SyncChange object for a tracked item.

    Args:
        state: Sync state for the item
        change_type: Type of change detected
        source: Where the change originated
        conflict: Whether this is a conflict

    Returns:
        New SyncChange instance
    """
    return SyncChange(
        memory_id=state.memory_id,
        obsidian_path=state.obsidian_path,
        vault=state.vault,
        change_type=change_type,
        source=source,
        openbrain_state=state if conflict else None,
        conflict=conflict,
    )


def _detect_new_obsidian_files(
    obsidian_files: set[str],
    tracked_paths: set[str],
    memory_map: dict[str, "MemoryOut"],
    vault: str,
) -> list[SyncChange]:
    """
    Find new files in Obsidian that are not yet tracked.

    Args:
        obsidian_files: Set of all files in Obsidian
        tracked_paths: Set of paths already being tracked
        memory_map: Map of obsidian_ref to MemoryOut
        vault: Vault name

    Returns:
        List of SyncChange objects for new files
    """
    changes: list[SyncChange] = []

    for file_path in obsidian_files:
        if file_path not in tracked_paths and file_path not in memory_map:
            changes.append(
                SyncChange(
                    memory_id="",
                    obsidian_path=file_path,
                    vault=vault,
                    change_type=ChangeType.CREATED,
                    source="obsidian",
                )
            )

    return changes


def _detect_new_openbrain_memories(
    memory_map: dict[str, "MemoryOut"],
    tracked_paths: set[str],
    since: datetime,
    vault: str,
) -> list[SyncChange]:
    """
    Find new memories in OpenBrain created since the given time.

    Args:
        memory_map: Map of obsidian_ref to MemoryOut
        tracked_paths: Set of paths already being tracked
        since: Only include memories updated after this time
        vault: Vault name

    Returns:
        List of SyncChange objects for new memories
    """
    changes: list[SyncChange] = []

    for path, memory in memory_map.items():
        if path not in tracked_paths and memory.updated_at > since:
            changes.append(
                SyncChange(
                    memory_id=memory.id,
                    obsidian_path=path,
                    vault=vault,
                    change_type=ChangeType.CREATED,
                    source="openbrain",
                )
            )

    return changes


class BidirectionalSyncEngine:
    """
    Engine for bidirectional synchronization between OpenBrain and Obsidian.
    """

    def __init__(
        self,
        strategy: SyncStrategy = SyncStrategy.DOMAIN_BASED,
        tracker: Optional[ObsidianChangeTracker] = None,
    ):
        self.strategy = strategy
        self.tracker = tracker or ObsidianChangeTracker()

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute hash of content for quick comparison."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]

    async def detect_changes(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        vault: str,
        since: Optional[datetime] = None,
    ) -> list[SyncChange]:
        """
        Detect changes between OpenBrain and Obsidian.

        Compares current state with last known sync state to identify:
        - New items in OpenBrain
        - New items in Obsidian
        - Modified items in either system
        - Deleted items
        """
        changes: list[SyncChange] = []
        since = since or datetime.min.replace(tzinfo=timezone.utc)

        # Fetch data from both systems
        memory_map = await _get_openbrain_memories(session, vault)
        obsidian_files = await _get_obsidian_files(adapter, vault)

        # Get tracked states for this vault
        tracked_states = [s for s in self.tracker.get_all_states() if s.vault == vault]

        # Process tracked items
        for state in tracked_states:
            memory = memory_map.get(state.obsidian_path)
            obsidian_exists = state.obsidian_path in obsidian_files

            # Check for changes
            memory_changed = _check_memory_changed(
                state, memory, self.compute_content_hash
            )
            # Obsidian change detection: file exists but we haven't tracked
            # a modification time comparison. In production, this should
            # compare mtime with obsidian_modified_at from state.
            obsidian_changed = False  # Simplified for now

            # Determine change type and create change record
            change = self._determine_change(
                state, memory, obsidian_exists, memory_changed, obsidian_changed
            )

            if change:
                changes.append(change)

        # Find new items
        tracked_paths = {s.obsidian_path for s in tracked_states}

        # New items in OpenBrain
        new_openbrain = _detect_new_openbrain_memories(
            memory_map, tracked_paths, since, vault
        )
        changes.extend(new_openbrain)

        # Find new items in Obsidian
        new_obsidian = _detect_new_obsidian_files(
            obsidian_files, tracked_paths, memory_map, vault
        )
        changes.extend(new_obsidian)

        return changes

    def _determine_change(
        self,
        state: SyncState,
        memory: "MemoryOut | None",
        obsidian_exists: bool,
        memory_changed: bool,
        obsidian_changed: bool,
    ) -> SyncChange | None:
        """
        Determine the type of change for a tracked item.

        Args:
            state: Last known sync state
            memory: Current memory from OpenBrain (None if deleted)
            obsidian_exists: Whether the file exists in Obsidian
            memory_changed: Whether OpenBrain content has changed
            obsidian_changed: Whether Obsidian content has changed

        Returns:
            SyncChange if a change is detected, None otherwise
        """
        # Both deleted
        if not memory and not obsidian_exists:
            change = _create_sync_change(state, ChangeType.DELETED, "both")
            self.tracker.remove_state(state.vault, state.obsidian_path)
            return change

        # Conflict: both changed
        if memory_changed and obsidian_changed:
            return _create_sync_change(state, ChangeType.UPDATED, "both", conflict=True)

        # Only OpenBrain changed
        if memory_changed:
            return _create_sync_change(state, ChangeType.UPDATED, "openbrain")

        # Only Obsidian changed
        if obsidian_changed:
            return _create_sync_change(state, ChangeType.UPDATED, "obsidian")

        # No change detected
        return None

    def resolve_conflict(
        self,
        change: SyncChange,
        memory: Optional["MemoryOut"] = None,
    ) -> Literal["openbrain", "obsidian", "manual"]:
        """
        Resolve conflict based on strategy.

        Returns which source should win.
        """
        if not change.conflict:
            return change.source if change.source != "both" else "openbrain"

        if self.strategy == SyncStrategy.LAST_WRITE_WINS:
            # Compare timestamps
            ob_time = (
                change.openbrain_state.memory_updated_at
                if change.openbrain_state
                else datetime.min
            )
            obs_time = (
                change.obsidian_state.obsidian_modified_at
                if change.obsidian_state
                else datetime.min
            )
            return "openbrain" if ob_time > obs_time else "obsidian"

        elif self.strategy == SyncStrategy.DOMAIN_BASED:
            # Corporate = OpenBrain wins, Personal = Obsidian wins
            if memory:
                if memory.domain == "corporate":
                    return "openbrain"
                elif memory.domain == "personal":
                    return "obsidian"
            # Default: OpenBrain wins for build domain
            return "openbrain"

        elif self.strategy == SyncStrategy.MANUAL_REVIEW:
            # Mark for manual review
            change.resolution = "manual_review_required"
            return "manual"

        return "openbrain"  # Default fallback

    async def _import_note_as_memory(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        change: SyncChange,
    ) -> None:
        """Import an Obsidian note into OpenBrain as a new memory (CREATED from obsidian)."""
        from .memory_writes import handle_memory_write
        from .schemas import MemoryWriteRequest, MemoryWriteRecord, WriteMode

        try:
            note = await adapter.read_note(change.vault, change.obsidian_path)
            record = MemoryWriteRecord(
                content=note.content,
                domain=note.frontmatter.get("domain", "personal"),
                entity_type=note.frontmatter.get("entity_type", "Note"),
                title=note.title,
                owner=note.frontmatter.get("owner", ""),
                tags=note.tags,
                obsidian_ref=note.path,
            )
            result = await handle_memory_write(
                session,
                MemoryWriteRequest(record=record, write_mode=WriteMode.upsert),
                actor="obsidian-sync",
            )
            if result.record:
                self.tracker.update_state(
                    SyncState(
                        memory_id=result.record.id,
                        obsidian_path=note.path,
                        vault=change.vault,
                        content_hash=self.compute_content_hash(note.content),
                        memory_updated_at=datetime.now(timezone.utc),
                        obsidian_modified_at=datetime.now(timezone.utc),
                    )
                )
        except Exception as e:
            log.error(
                "import_from_obsidian_failed: vault=%s path=%s error=%s",
                change.vault,
                change.obsidian_path,
                str(e),
            )
            raise ObsidianCliError(
                f"Failed to import from Obsidian: {e}",
                details={"vault": change.vault, "path": change.obsidian_path},
            ) from e

    async def _update_memory_from_obsidian(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        change: SyncChange,
    ) -> None:
        """Update an existing memory from an Obsidian note (obsidian-wins conflict resolution)."""
        from .memory_writes import update_memory
        from .schemas import MemoryUpdate

        if not change.memory_id:
            raise ObsidianCliError(
                "Cannot update memory: memory_id is missing from SyncChange",
                details={"vault": change.vault, "path": change.obsidian_path},
            )
        try:
            note = await adapter.read_note(change.vault, change.obsidian_path)
            data = MemoryUpdate(
                content=note.content,
                title=note.frontmatter.get("title"),
                tags=note.tags or [],
                obsidian_ref=note.path,
                updated_by="obsidian-sync",
            )
            updated = await update_memory(
                session, change.memory_id, data, actor="obsidian-sync"
            )
            if updated is None:
                log.warning(
                    "update_from_obsidian_memory_not_found: memory_id=%s vault=%s path=%s",
                    change.memory_id,
                    change.vault,
                    change.obsidian_path,
                )
            else:
                log.info(
                    "update_from_obsidian_success: memory_id=%s vault=%s path=%s",
                    change.memory_id,
                    change.vault,
                    change.obsidian_path,
                )
        except ObsidianCliError:
            raise
        except Exception as e:
            log.error(
                "update_from_obsidian_failed: memory_id=%s error=%s vault=%s path=%s",
                change.memory_id,
                str(e),
                change.vault,
                change.obsidian_path,
            )
            raise ObsidianCliError(
                f"Failed to update from Obsidian: {e}",
                details={"vault": change.vault, "path": change.obsidian_path},
            ) from e

    async def apply_sync(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        change: SyncChange,
    ) -> bool:
        """Apply a single sync change. Returns True if successful, False if deferred."""
        try:
            if change.change_type == ChangeType.CREATED:
                if change.source == "obsidian":
                    await self._import_note_as_memory(session, adapter, change)
                # change.source == "openbrain": export to Obsidian (not yet implemented)

            elif change.change_type == ChangeType.UPDATED:
                resolution = self.resolve_conflict(change)
                if resolution == "manual":
                    return False
                if resolution != "openbrain":  # obsidian wins
                    await self._update_memory_from_obsidian(session, adapter, change)
                # resolution == "openbrain": push to Obsidian (not yet implemented)

            # ChangeType.DELETED: not yet implemented

            return True

        except Exception as e:
            log.error(
                "apply_sync_failed: change_type=%s error=%s",
                change.change_type.value if change else None,
                str(e),
            )
            raise

    async def sync(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        vault: str,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Perform full bidirectional sync.

        Args:
            session: Database session
            adapter: Obsidian adapter
            vault: Target vault
            dry_run: If True, only detect changes without applying

        Returns:
            SyncResult with details of what was done
        """
        result = SyncResult(started_at=datetime.now(timezone.utc))

        # 1. Detect changes
        log.info("Detecting changes for vault: %s", vault)
        changes = await self.detect_changes(session, adapter, vault)
        result.changes_detected = len(changes)
        result.details = changes

        conflicts = [c for c in changes if c.conflict]
        result.conflicts = len(conflicts)

        log.info("Detected: %d changes, %d conflicts", len(changes), len(conflicts))

        if dry_run:
            log.info("Dry run - no changes applied")
            result.completed_at = datetime.now(timezone.utc)
            return result

        # 2. Apply changes
        log.info("Applying changes...")
        for change in changes:
            if change.conflict and self.strategy == SyncStrategy.MANUAL_REVIEW:
                log.warning(
                    "Skipping conflict (manual review): %s", change.obsidian_path
                )
                continue

            success = await self.apply_sync(session, adapter, change)
            if success:
                result.changes_applied += 1
            else:
                result.errors.append(
                    {
                        "path": change.obsidian_path,
                        "error": "Failed to apply change",
                    }
                )

        result.completed_at = datetime.now(timezone.utc)

        log.info("Applied: %d, Errors: %d", result.changes_applied, len(result.errors))

        return result
