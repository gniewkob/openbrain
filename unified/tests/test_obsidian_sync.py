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
