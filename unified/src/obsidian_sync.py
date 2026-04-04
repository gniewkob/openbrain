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
        return {
            "memory_id": self.memory_id,
            "obsidian_path": self.obsidian_path,
            "vault": self.vault,
            "content_hash": self.content_hash,
            "memory_updated_at": self.memory_updated_at.isoformat() if self.memory_updated_at else None,
            "obsidian_modified_at": self.obsidian_modified_at.isoformat() if self.obsidian_modified_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncState":
        return cls(
            memory_id=data["memory_id"],
            obsidian_path=data["obsidian_path"],
            vault=data["vault"],
            content_hash=data["content_hash"],
            memory_updated_at=datetime.fromisoformat(data["memory_updated_at"]) if data.get("memory_updated_at") else datetime.now(timezone.utc),
            obsidian_modified_at=datetime.fromisoformat(data["obsidian_modified_at"]) if data.get("obsidian_modified_at") else datetime.now(timezone.utc),
            last_sync_at=datetime.fromisoformat(data["last_sync_at"]) if data.get("last_sync_at") else None,
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
        return {
            "memory_id": self.memory_id,
            "obsidian_path": self.obsidian_path,
            "vault": self.vault,
            "change_type": self.change_type.value,
            "source": self.source,
            "openbrain_state": self.openbrain_state.to_dict() if self.openbrain_state else None,
            "obsidian_state": self.obsidian_state.to_dict() if self.obsidian_state else None,
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
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
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
                with open(self.storage_path, 'r', encoding='utf-8') as f:
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
        with open(self.storage_path, 'w', encoding='utf-8') as f:
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
            1 for s in self._state.values() 
            if s.last_sync_at and (now - s.last_sync_at).days < 7
        )
        
        return {
            "total_tracked": total,
            "never_synced": never_synced,
            "synced_recently": synced_recently,
            "storage_path": self.storage_path,
        }


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
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]
    
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
        from .memory_reads import list_memories
        
        changes: list[SyncChange] = []
        since = since or datetime.min.replace(tzinfo=timezone.utc)
        
        # Get all memories from OpenBrain that have obsidian_ref
        # This is a simplified version - in production, we'd need to track
        # which memories are linked to Obsidian notes
        all_memories = await list_memories(session, {}, limit=1000)
        
        # Get all notes from Obsidian vault
        try:
            obsidian_files = await adapter.list_files(vault, limit=1000)
        except Exception as e:
            log.warning("obsidian_list_files_failed", error=str(e), vault=vault)
            obsidian_files = []
        
        # Build lookup maps
        memory_map: dict[str, MemoryOut] = {
            m.obsidian_ref: m for m in all_memories if m.obsidian_ref
        }
        
        # Check each tracked item
        for state in self.tracker.get_all_states():
            if state.vault != vault:
                continue
            
            memory = memory_map.get(state.obsidian_path)
            obsidian_exists = state.obsidian_path in obsidian_files
            
            # Check OpenBrain changes
            memory_changed = False
            if memory:
                current_hash = self.compute_content_hash(memory.content)
                if current_hash != state.content_hash:
                    memory_changed = True
                if memory.updated_at and memory.updated_at > state.memory_updated_at:
                    memory_changed = True
            
            # Check Obsidian changes (simplified - in production, check mtime)
            obsidian_changed = state.obsidian_path in obsidian_files
            
            # Determine change type
            if not memory and not obsidian_exists:
                # Both deleted
                change = SyncChange(
                    memory_id=state.memory_id,
                    obsidian_path=state.obsidian_path,
                    vault=vault,
                    change_type=ChangeType.DELETED,
                    source="both",
                )
                changes.append(change)
                self.tracker.remove_state(vault, state.obsidian_path)
            
            elif memory_changed and obsidian_changed:
                # Conflict: both changed
                change = SyncChange(
                    memory_id=state.memory_id,
                    obsidian_path=state.obsidian_path,
                    vault=vault,
                    change_type=ChangeType.UPDATED,
                    source="both",
                    openbrain_state=state,
                    conflict=True,
                )
                changes.append(change)
            
            elif memory_changed:
                # Only OpenBrain changed
                change = SyncChange(
                    memory_id=state.memory_id,
                    obsidian_path=state.obsidian_path,
                    vault=vault,
                    change_type=ChangeType.UPDATED,
                    source="openbrain",
                )
                changes.append(change)
            
            elif obsidian_changed:
                # Only Obsidian changed
                change = SyncChange(
                    memory_id=state.memory_id,
                    obsidian_path=state.obsidian_path,
                    vault=vault,
                    change_type=ChangeType.UPDATED,
                    source="obsidian",
                )
                changes.append(change)
        
        # Find new items in OpenBrain
        tracked_paths = {s.obsidian_path for s in self.tracker.get_all_states()}
        for path, memory in memory_map.items():
            if path not in tracked_paths and memory.updated_at > since:
                change = SyncChange(
                    memory_id=memory.id,
                    obsidian_path=path,
                    vault=vault,
                    change_type=ChangeType.CREATED,
                    source="openbrain",
                )
                changes.append(change)
        
        # Find new items in Obsidian (files not yet tracked)
        for file_path in obsidian_files:
            if file_path not in tracked_paths and file_path not in memory_map:
                # New file in Obsidian - might need to import
                change = SyncChange(
                    memory_id="",
                    obsidian_path=file_path,
                    vault=vault,
                    change_type=ChangeType.CREATED,
                    source="obsidian",
                )
                changes.append(change)
        
        return changes
    
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
            ob_time = change.openbrain_state.memory_updated_at if change.openbrain_state else datetime.min
            obs_time = change.obsidian_state.obsidian_modified_at if change.obsidian_state else datetime.min
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
    
    async def apply_sync(
        self,
        session: "AsyncSession",
        adapter: "ObsidianCliAdapter",
        change: SyncChange,
    ) -> bool:
        """
        Apply a sync change.
        
        Returns True if successful, False otherwise.
        """
        from .memory_writes import handle_memory_write
        from .schemas import MemoryWriteRequest, MemoryWriteRecord, WriteMode
        
        try:
            if change.change_type == ChangeType.CREATED:
                if change.source == "openbrain":
                    # Export from OpenBrain to Obsidian
                    # This would need the actual memory content
                    pass
                
                elif change.source == "obsidian":
                    # Import from Obsidian to OpenBrain
                    try:
                        note = await adapter.read_note(change.vault, change.obsidian_path)
                        
                        # Create memory from note
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
                            # Update tracker
                            state = SyncState(
                                memory_id=result.record.id,
                                obsidian_path=note.path,
                                vault=change.vault,
                                content_hash=self.compute_content_hash(note.content),
                                memory_updated_at=datetime.now(timezone.utc),
                                obsidian_modified_at=datetime.now(timezone.utc),
                            )
                            self.tracker.update_state(state)
                        
                        return True
                    except Exception as e:
                        log.error("import_from_obsidian_failed", error=str(e), vault=change.vault, path=change.obsidian_path)
                        raise ObsidianCliError(
                            f"Failed to import from Obsidian: {e}",
                            details={"vault": change.vault, "path": change.obsidian_path},
                        ) from e
            
            elif change.change_type == ChangeType.UPDATED:
                resolution = self.resolve_conflict(change)
                
                if resolution == "manual":
                    # Skip for now, will be handled manually
                    return False
                
                if resolution == "openbrain":
                    # Update Obsidian from OpenBrain
                    pass  # Would need actual memory
                
                else:  # obsidian wins
                    # Update OpenBrain from Obsidian
                    try:
                        note = await adapter.read_note(change.vault, change.obsidian_path)
                        
                        # Update existing memory
                        # This would need the memory_id lookup
                        pass
                    except Exception as e:
                        log.error("update_from_obsidian_failed", error=str(e), vault=change.vault, path=change.obsidian_path)
                        raise ObsidianCliError(
                            f"Failed to update from Obsidian: {e}",
                            details={"vault": change.vault, "path": change.obsidian_path},
                        ) from e
            
            elif change.change_type == ChangeType.DELETED:
                # Handle deletions
                pass
            
            return True
        
        except Exception as e:
            log.error("apply_sync_failed", error=str(e), change_type=change.change_type.value if change else None)
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
                log.warning("Skipping conflict (manual review): %s", change.obsidian_path)
                continue
            
            success = await self.apply_sync(session, adapter, change)
            if success:
                result.changes_applied += 1
            else:
                result.errors.append({
                    "path": change.obsidian_path,
                    "error": "Failed to apply change",
                })
        
        result.completed_at = datetime.now(timezone.utc)
        
        log.info("Applied: %d, Errors: %d", result.changes_applied, len(result.errors))
        
        return result
