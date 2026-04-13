"""Tests for obsidian_sync module."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.obsidian_sync import (
    BidirectionalSyncEngine,
    ChangeType,
    ObsidianChangeTracker,
    SyncChange,
    SyncState,
    SyncStrategy,
)


class TestObsidianChangeTracker:
    """Tests for ObsidianChangeTracker."""

    def test_init_creates_empty_state(self, tmp_path):
        """Test that tracker initializes with empty state."""
        storage_path = tmp_path / "sync_state.json"
        tracker = ObsidianChangeTracker(storage_path=str(storage_path))
        
        assert tracker.get_all_states() == []
        assert tracker.get_stats()["total_tracked"] == 0

    def test_update_and_get_state(self, tmp_path):
        """Test updating and retrieving state."""
        storage_path = tmp_path / "sync_state.json"
        tracker = ObsidianChangeTracker(storage_path=str(storage_path))
        
        state = SyncState(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            content_hash="abc123",
            memory_updated_at=datetime.now(timezone.utc),
            obsidian_modified_at=datetime.now(timezone.utc),
        )
        
        tracker.update_state(state)
        
        retrieved = tracker.get_state("Documents", "test.md")
        assert retrieved is not None
        assert retrieved.memory_id == "mem-1"
        assert retrieved.obsidian_path == "test.md"

    def test_remove_state(self, tmp_path):
        """Test removing state."""
        storage_path = tmp_path / "sync_state.json"
        tracker = ObsidianChangeTracker(storage_path=str(storage_path))
        
        state = SyncState(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            content_hash="abc123",
            memory_updated_at=datetime.now(timezone.utc),
            obsidian_modified_at=datetime.now(timezone.utc),
        )
        
        tracker.update_state(state)
        assert tracker.get_state("Documents", "test.md") is not None
        
        tracker.remove_state("Documents", "test.md")
        assert tracker.get_state("Documents", "test.md") is None

    def test_persistence(self, tmp_path):
        """Test that state is persisted to disk."""
        storage_path = tmp_path / "sync_state.json"
        
        # Create tracker and add state
        tracker1 = ObsidianChangeTracker(storage_path=str(storage_path))
        state = SyncState(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            content_hash="abc123",
            memory_updated_at=datetime.now(timezone.utc),
            obsidian_modified_at=datetime.now(timezone.utc),
        )
        tracker1.update_state(state)
        
        # Create new tracker instance with same storage
        tracker2 = ObsidianChangeTracker(storage_path=str(storage_path))
        retrieved = tracker2.get_state("Documents", "test.md")
        
        assert retrieved is not None
        assert retrieved.memory_id == "mem-1"


class TestBidirectionalSyncEngineInit:
    """Tests for BidirectionalSyncEngine initialization."""

    def test_default_initialization(self):
        """Test default engine initialization."""
        engine = BidirectionalSyncEngine()
        
        assert engine.strategy == SyncStrategy.DOMAIN_BASED
        assert engine.tracker is not None

    def test_custom_strategy(self):
        """Test engine with custom strategy."""
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.LAST_WRITE_WINS)
        
        assert engine.strategy == SyncStrategy.LAST_WRITE_WINS

    def test_custom_tracker(self, tmp_path):
        """Test engine with custom tracker."""
        tracker = ObsidianChangeTracker(storage_path=str(tmp_path / "sync.json"))
        engine = BidirectionalSyncEngine(tracker=tracker)
        
        assert engine.tracker is tracker


class TestComputeContentHash:
    """Tests for content hash computation."""

    def test_hash_is_consistent(self):
        """Test that hash is consistent for same content."""
        content = "Test content"
        hash1 = BidirectionalSyncEngine.compute_content_hash(content)
        hash2 = BidirectionalSyncEngine.compute_content_hash(content)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # First 32 chars of SHA256

    def test_hash_differs_for_different_content(self):
        """Test that different content produces different hash."""
        hash1 = BidirectionalSyncEngine.compute_content_hash("Content A")
        hash2 = BidirectionalSyncEngine.compute_content_hash("Content B")
        
        assert hash1 != hash2


class TestDetectChangesEmptyState:
    """Tests for detect_changes with empty state."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp storage."""
        tracker = ObsidianChangeTracker(storage_path=str(tmp_path / "sync.json"))
        return BidirectionalSyncEngine(tracker=tracker)

    @pytest.fixture
    def mock_adapter(self):
        """Create mock adapter."""
        adapter = MagicMock()
        adapter.list_files = AsyncMock(return_value=[])
        return adapter

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_no_changes_when_empty(self, engine, mock_session, mock_adapter):
        """Test no changes detected when both systems are empty."""
        with patch("src.obsidian_sync.list_memories", new=AsyncMock(return_value=[])):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        assert changes == []

    @pytest.mark.asyncio
    async def test_detect_new_openbrain_memory(self, engine, mock_session, mock_adapter):
        """Test detecting new memory in OpenBrain."""
        # Use past date for 'since' to include the new memory
        past = datetime.min.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        
        # Mock memory in OpenBrain
        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.obsidian_ref = "test.md"
        mock_memory.content = "Test content"
        mock_memory.updated_at = now
        
        with patch(
            "src.obsidian_sync.list_memories", new=AsyncMock(return_value=[mock_memory])
        ):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents", since=past
            )
        
        # Should detect as new OpenBrain memory
        openbrain_changes = [c for c in changes if c.source == "openbrain"]
        assert len(openbrain_changes) == 1
        assert openbrain_changes[0].change_type == ChangeType.CREATED
        assert openbrain_changes[0].memory_id == "mem-1"
        assert openbrain_changes[0].obsidian_path == "test.md"

    @pytest.mark.asyncio
    async def test_detect_new_obsidian_file(self, engine, mock_session, mock_adapter):
        """Test detecting new file in Obsidian."""
        mock_adapter.list_files = AsyncMock(return_value=["new_file.md"])
        
        with patch("src.obsidian_sync.list_memories", new=AsyncMock(return_value=[])):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        # Should detect as new Obsidian file
        obsidian_changes = [c for c in changes if c.source == "obsidian"]
        assert len(obsidian_changes) >= 1
        assert obsidian_changes[0].change_type == ChangeType.CREATED
        assert obsidian_changes[0].obsidian_path == "new_file.md"

    @pytest.mark.asyncio
    async def test_list_files_failure_handled(self, engine, mock_session, mock_adapter):
        """Test that list_files failure is handled gracefully."""
        mock_adapter.list_files = AsyncMock(side_effect=Exception("Connection error"))
        
        with patch("src.obsidian_sync.list_memories", new=AsyncMock(return_value=[])):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        # Should return empty list when Obsidian is unreachable
        assert changes == []


class TestDetectChangesWithTrackedState:
    """Tests for detect_changes with existing tracked state."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp storage and tracked state."""
        tracker = ObsidianChangeTracker(storage_path=str(tmp_path / "sync.json"))
        
        # Add tracked state
        state = SyncState(
            memory_id="mem-1",
            obsidian_path="tracked.md",
            vault="Documents",
            content_hash=BidirectionalSyncEngine.compute_content_hash("Original content"),
            memory_updated_at=datetime.now(timezone.utc),
            obsidian_modified_at=datetime.now(timezone.utc),
        )
        tracker.update_state(state)
        
        return BidirectionalSyncEngine(tracker=tracker)

    @pytest.fixture
    def mock_adapter(self):
        """Create mock adapter."""
        adapter = MagicMock()
        adapter.list_files = AsyncMock(return_value=["tracked.md"])
        return adapter

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_no_change_when_unchanged(self, engine, mock_session, mock_adapter):
        """Test no change detected when content is unchanged."""
        # Mock memory with same content
        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.obsidian_ref = "tracked.md"
        mock_memory.content = "Original content"
        # Use same updated_at as when state was created
        mock_memory.updated_at = datetime.min.replace(tzinfo=timezone.utc)
        
        with patch(
            "src.obsidian_sync.list_memories", new=AsyncMock(return_value=[mock_memory])
        ):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        # Should detect no changes
        assert changes == []

    @pytest.mark.asyncio
    async def test_detect_openbrain_change(self, engine, mock_session, mock_adapter):
        """Test detecting change in OpenBrain content."""
        # Mock memory with different content
        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.obsidian_ref = "tracked.md"
        mock_memory.content = "Modified content"
        mock_memory.updated_at = datetime.now(timezone.utc)
        
        with patch(
            "src.obsidian_sync.list_memories", new=AsyncMock(return_value=[mock_memory])
        ):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        # Should detect content change from OpenBrain
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.UPDATED
        assert changes[0].source == "openbrain"

    @pytest.mark.asyncio
    async def test_detect_obsidian_change(self, engine, mock_session, mock_adapter):
        """Test detecting change in Obsidian - currently simplified."""
        # Mock memory with same content (no OpenBrain change)
        mock_memory = MagicMock()
        mock_memory.id = "mem-1"
        mock_memory.obsidian_ref = "tracked.md"
        mock_memory.content = "Original content"
        mock_memory.updated_at = datetime.min.replace(tzinfo=timezone.utc)
        
        # File exists in Obsidian, but current simplified implementation
        # doesn't detect Obsidian changes without mtime comparison
        with patch(
            "src.obsidian_sync.list_memories", new=AsyncMock(return_value=[mock_memory])
        ):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        # No changes detected - Obsidian change detection is simplified
        assert changes == []

    @pytest.mark.asyncio
    async def test_detect_both_deleted(self, engine, mock_session, mock_adapter):
        """Test detecting when both systems have deleted the item."""
        # No memory in OpenBrain and file not in Obsidian
        mock_adapter.list_files = AsyncMock(return_value=[])
        
        with patch("src.obsidian_sync.list_memories", new=AsyncMock(return_value=[])):
            changes = await engine.detect_changes(
                mock_session, mock_adapter, "Documents"
            )
        
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.DELETED
        assert changes[0].source == "both"

    @pytest.mark.asyncio
    async def test_state_removed_after_both_deleted(self, engine, mock_session, mock_adapter):
        """Test that tracked state is removed after detecting both deleted."""
        mock_adapter.list_files = AsyncMock(return_value=[])
        
        with patch("src.obsidian_sync.list_memories", new=AsyncMock(return_value=[])):
            await engine.detect_changes(mock_session, mock_adapter, "Documents")
        
        # State should be removed from tracker
        assert engine.tracker.get_state("Documents", "tracked.md") is None


class TestSyncChange:
    """Tests for SyncChange dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        change = SyncChange(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            change_type=ChangeType.CREATED,
            source="openbrain",
        )
        
        data = change.to_dict()
        
        assert data["memory_id"] == "mem-1"
        assert data["obsidian_path"] == "test.md"
        assert data["vault"] == "Documents"
        assert data["change_type"] == "created"
        assert data["source"] == "openbrain"
        assert data["conflict"] is False

    def test_to_dict_with_conflict(self):
        """Test conversion with conflict flag."""
        change = SyncChange(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            change_type=ChangeType.UPDATED,
            source="both",
            conflict=True,
        )
        
        data = change.to_dict()
        
        assert data["conflict"] is True
        assert data["source"] == "both"


class TestResolveConflict:
    """Tests for conflict resolution."""

    def test_no_conflict_returns_source(self):
        """Test that non-conflict returns the source."""
        engine = BidirectionalSyncEngine()
        change = SyncChange(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            change_type=ChangeType.UPDATED,
            source="openbrain",
            conflict=False,
        )
        
        result = engine.resolve_conflict(change)
        
        assert result == "openbrain"

    def test_conflict_defaults_to_openbrain(self):
        """Test that conflict defaults to openbrain."""
        engine = BidirectionalSyncEngine()
        change = SyncChange(
            memory_id="mem-1",
            obsidian_path="test.md",
            vault="Documents",
            change_type=ChangeType.UPDATED,
            source="both",
            conflict=True,
        )
        
        result = engine.resolve_conflict(change)
        
        assert result == "openbrain"


# ---------------------------------------------------------------------------
# Additional coverage: SyncResult.to_dict, _load_state error, _check_memory_changed
# resolve_conflict strategies, apply_sync, sync
# ---------------------------------------------------------------------------


class TestSyncResultToDict:
    """Tests for SyncResult.to_dict."""

    def test_to_dict_with_completed_at(self):
        from src.obsidian_sync import SyncResult

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = SyncResult(started_at=now, completed_at=now)
        d = result.to_dict()
        assert d["started_at"] == now.isoformat()
        assert d["completed_at"] == now.isoformat()
        assert d["changes_detected"] == 0


class TestLoadStateError:
    """Tests for _load_state error recovery."""

    def test_corrupted_json_resets_state(self, tmp_path):
        import json

        storage_path = tmp_path / "sync_state.json"
        storage_path.write_text("{{invalid json{{")

        tracker = ObsidianChangeTracker(storage_path=str(storage_path))
        # should not raise, state should be empty
        assert tracker.get_all_states() == []


class TestCheckMemoryChanged:
    """Tests for _check_memory_changed module-level function."""

    def test_returns_true_when_updated_at_is_newer(self):
        from src.obsidian_sync import _check_memory_changed

        past = datetime(2026, 1, 1, tzinfo=timezone.utc)
        future = datetime(2026, 6, 1, tzinfo=timezone.utc)

        state = SyncState(
            memory_id="m1",
            obsidian_path="n.md",
            vault="v",
            content_hash="same_hash",  # hashes match
            memory_updated_at=past,
            obsidian_modified_at=past,
        )
        memory = MagicMock()
        memory.content = "content"
        memory.updated_at = future

        result = _check_memory_changed(state, memory, lambda c: "same_hash")
        assert result is True


class TestResolveConflictStrategies:
    """Tests for all resolve_conflict strategy branches."""

    def _change(self, conflict=True, source="both"):
        return SyncChange(
            memory_id="m1",
            obsidian_path="test.md",
            vault="v",
            change_type=ChangeType.UPDATED,
            source=source,
            conflict=conflict,
        )

    def test_last_write_wins_openbrain_newer(self):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.LAST_WRITE_WINS)
        change = self._change()
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        old = datetime(2026, 1, 1, tzinfo=timezone.utc)
        change.openbrain_state = SyncState(
            memory_id="m1", obsidian_path="test.md", vault="v",
            content_hash="h", memory_updated_at=now, obsidian_modified_at=old,
        )
        change.obsidian_state = SyncState(
            memory_id="m1", obsidian_path="test.md", vault="v",
            content_hash="h", memory_updated_at=old, obsidian_modified_at=old,
        )
        assert engine.resolve_conflict(change) == "openbrain"

    def test_last_write_wins_obsidian_newer(self):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.LAST_WRITE_WINS)
        change = self._change()
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        old = datetime(2026, 1, 1, tzinfo=timezone.utc)
        change.openbrain_state = SyncState(
            memory_id="m1", obsidian_path="test.md", vault="v",
            content_hash="h", memory_updated_at=old, obsidian_modified_at=old,
        )
        change.obsidian_state = SyncState(
            memory_id="m1", obsidian_path="test.md", vault="v",
            content_hash="h", memory_updated_at=old, obsidian_modified_at=now,
        )
        assert engine.resolve_conflict(change) == "obsidian"

    def test_domain_based_corporate_wins_openbrain(self):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)
        change = self._change()
        memory = MagicMock()
        memory.domain = "corporate"
        assert engine.resolve_conflict(change, memory=memory) == "openbrain"

    def test_domain_based_personal_wins_obsidian(self):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)
        change = self._change()
        memory = MagicMock()
        memory.domain = "personal"
        assert engine.resolve_conflict(change, memory=memory) == "obsidian"

    def test_manual_review_returns_manual(self):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.MANUAL_REVIEW)
        change = self._change()
        assert engine.resolve_conflict(change) == "manual"
        assert change.resolution == "manual_review_required"

    def test_no_conflict_source_both_returns_openbrain(self):
        engine = BidirectionalSyncEngine()
        change = self._change(conflict=False, source="both")
        assert engine.resolve_conflict(change) == "openbrain"


class TestApplySync:
    """Tests for BidirectionalSyncEngine.apply_sync."""

    def _engine(self, tmp_path):
        storage_path = tmp_path / "sync_state.json"
        tracker = ObsidianChangeTracker(storage_path=str(storage_path))
        return BidirectionalSyncEngine(tracker=tracker)

    def _change(self, change_type=ChangeType.CREATED, source="obsidian"):
        return SyncChange(
            memory_id="m1",
            obsidian_path="Notes/test.md",
            vault="my-vault",
            change_type=change_type,
            source=source,
            conflict=False,
        )

    @pytest.mark.asyncio
    async def test_created_openbrain_returns_true(self, tmp_path):
        engine = self._engine(tmp_path)
        session = AsyncMock()
        adapter = MagicMock()
        change = self._change(source="openbrain")
        # openbrain source created = pass (stub)
        result = await engine.apply_sync(session, adapter, change)
        assert result is True

    @pytest.mark.asyncio
    async def test_created_obsidian_imports_note(self, tmp_path):
        from src.common.obsidian_adapter import ObsidianNote

        engine = self._engine(tmp_path)
        session = AsyncMock()
        note = ObsidianNote(
            vault="my-vault", path="Notes/test.md", title="Test",
            content="# Test", frontmatter={"domain": "build", "owner": "alice"},
            tags=["test"], file_hash="abc",
        )
        adapter = MagicMock()
        adapter.read_note = AsyncMock(return_value=note)

        change = self._change(source="obsidian")

        mock_result = MagicMock()
        mock_result.record = MagicMock()
        mock_result.record.id = "new-id"

        # handle_memory_write is a local import inside apply_sync, patch at source module
        with patch("src.memory_writes.handle_memory_write", AsyncMock(return_value=mock_result)):
            result = await engine.apply_sync(session, adapter, change)
        assert result is True

    @pytest.mark.asyncio
    async def test_updated_manual_returns_false(self, tmp_path):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.MANUAL_REVIEW)
        session = AsyncMock()
        adapter = MagicMock()
        change = self._change(change_type=ChangeType.UPDATED, source="both")
        change.conflict = True
        result = await engine.apply_sync(session, adapter, change)
        assert result is False

    @pytest.mark.asyncio
    async def test_updated_openbrain_wins_returns_true(self, tmp_path):
        engine = self._engine(tmp_path)
        session = AsyncMock()
        adapter = MagicMock()
        change = self._change(change_type=ChangeType.UPDATED, source="openbrain")
        result = await engine.apply_sync(session, adapter, change)
        assert result is True

    @pytest.mark.asyncio
    async def test_deleted_returns_true(self, tmp_path):
        engine = self._engine(tmp_path)
        session = AsyncMock()
        adapter = MagicMock()
        change = self._change(change_type=ChangeType.DELETED)
        result = await engine.apply_sync(session, adapter, change)
        assert result is True


class TestSyncMethod:
    """Tests for BidirectionalSyncEngine.sync."""

    def _engine(self):
        return BidirectionalSyncEngine()

    @pytest.mark.asyncio
    async def test_dry_run_returns_without_applying(self, tmp_path):
        engine = self._engine()
        session = AsyncMock()
        adapter = MagicMock()
        change = SyncChange(
            memory_id="m1", obsidian_path="test.md", vault="v",
            change_type=ChangeType.UPDATED, source="openbrain", conflict=False,
        )
        with patch.object(engine, "detect_changes", AsyncMock(return_value=[change])):
            result = await engine.sync(session, adapter, "my-vault", dry_run=True)
        assert result.changes_detected == 1
        assert result.changes_applied == 0
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_sync_applies_changes(self, tmp_path):
        engine = self._engine()
        session = AsyncMock()
        adapter = MagicMock()
        change = SyncChange(
            memory_id="m1", obsidian_path="test.md", vault="v",
            change_type=ChangeType.UPDATED, source="openbrain", conflict=False,
        )
        with (
            patch.object(engine, "detect_changes", AsyncMock(return_value=[change])),
            patch.object(engine, "apply_sync", AsyncMock(return_value=True)),
        ):
            result = await engine.sync(session, adapter, "my-vault")
        assert result.changes_applied == 1
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_sync_records_failed_change(self, tmp_path):
        engine = self._engine()
        session = AsyncMock()
        adapter = MagicMock()
        change = SyncChange(
            memory_id="m1", obsidian_path="fail.md", vault="v",
            change_type=ChangeType.UPDATED, source="openbrain", conflict=False,
        )
        with (
            patch.object(engine, "detect_changes", AsyncMock(return_value=[change])),
            patch.object(engine, "apply_sync", AsyncMock(return_value=False)),
        ):
            result = await engine.sync(session, adapter, "my-vault")
        assert result.changes_applied == 0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_sync_skips_manual_review_conflicts(self, tmp_path):
        engine = BidirectionalSyncEngine(strategy=SyncStrategy.MANUAL_REVIEW)
        session = AsyncMock()
        adapter = MagicMock()
        change = SyncChange(
            memory_id="m1", obsidian_path="conflict.md", vault="v",
            change_type=ChangeType.UPDATED, source="both", conflict=True,
        )
        apply_mock = AsyncMock(return_value=True)
        with (
            patch.object(engine, "detect_changes", AsyncMock(return_value=[change])),
            patch.object(engine, "apply_sync", apply_mock),
        ):
            result = await engine.sync(session, adapter, "my-vault")
        # manual review conflict should be skipped, apply_sync not called
        apply_mock.assert_not_called()
        assert result.changes_applied == 0
