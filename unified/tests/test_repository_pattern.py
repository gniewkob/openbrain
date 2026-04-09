"""
Tests for Repository Pattern implementation (ARCH-002).
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from src.repositories import InMemoryMemoryRepository
from src.models import Memory


class MockMemoryCreate:
    """Mock Pydantic-like model for testing."""
    def __init__(self, **kwargs):
        self._data = kwargs
    
    def model_dump(self, exclude_unset: bool = False, exclude_defaults: bool = False):
        return self._data.copy()


class MockMemoryUpdate:
    """Mock Pydantic-like update model for testing."""
    def __init__(self, **kwargs):
        self._data = kwargs
    
    def model_dump(self, exclude_unset: bool = False, exclude_defaults: bool = False):
        return self._data.copy()


class TestInMemoryMemoryRepository(unittest.TestCase):
    """Unit tests for InMemoryMemoryRepository."""

    def setUp(self) -> None:
        self.repo = InMemoryMemoryRepository()

    def test_get_by_id_not_found(self) -> None:
        """Test getting non-existent memory returns None."""
        result = asyncio.run(self.repo.get_by_id("non-existent"))
        self.assertIsNone(result)

    def test_create_and_get_by_id(self) -> None:
        """Test creating and retrieving a memory."""
        # Create memory
        data = MockMemoryCreate(
            content="Test content",
            domain="build",
            entity_type="Test",
            match_key="test-key-1",
        )
        memory = asyncio.run(self.repo.create(data))
        
        self.assertIsNotNone(memory.id)
        self.assertEqual(memory.content, "Test content")
        
        # Retrieve by ID
        retrieved = asyncio.run(self.repo.get_by_id(memory.id))
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, memory.id)
        self.assertEqual(retrieved.content, "Test content")

    def test_get_by_match_key(self) -> None:
        """Test retrieving by match_key."""
        data = MockMemoryCreate(
            content="Test content",
            domain="build",
            entity_type="Test",
            match_key="unique-match-key",
        )
        memory = asyncio.run(self.repo.create(data))
        
        # Retrieve by match_key
        retrieved = asyncio.run(self.repo.get_by_match_key("unique-match-key"))
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, memory.id)

    def test_list_all_with_filters(self) -> None:
        """Test listing with domain and status filters."""
        # Create test memories
        for i in range(3):
            data = MockMemoryCreate(
                content=f"Content {i}",
                domain="build" if i < 2 else "personal",
                entity_type="Test",
                match_key=f"key-{i}",
                status="active" if i < 2 else "archived",
            )
            asyncio.run(self.repo.create(data))
        
        # List all
        all_memories = asyncio.run(self.repo.list_all())
        self.assertEqual(len(all_memories), 3)
        
        # Filter by domain
        build_memories = asyncio.run(self.repo.list_all(domain="build"))
        self.assertEqual(len(build_memories), 2)
        
        # Filter by status
        active_memories = asyncio.run(self.repo.list_all(status="active"))
        self.assertEqual(len(active_memories), 2)

    def test_count(self) -> None:
        """Test counting memories."""
        # Create test memories
        for i in range(3):
            data = MockMemoryCreate(
                content=f"Content {i}",
                domain="build" if i < 2 else "personal",
                entity_type="Test",
                match_key=f"key-{i}",
            )
            asyncio.run(self.repo.create(data))
        
        self.assertEqual(asyncio.run(self.repo.count()), 3)
        self.assertEqual(asyncio.run(self.repo.count(domain="build")), 2)
        self.assertEqual(asyncio.run(self.repo.count(domain="personal")), 1)

    def test_update(self) -> None:
        """Test updating a memory."""
        # Create memory
        data = MockMemoryCreate(
            content="Original content",
            domain="build",
            entity_type="Test",
            match_key="update-test",
        )
        memory = asyncio.run(self.repo.create(data))
        
        # Update
        update_data = MockMemoryUpdate(content="Updated content")
        updated = asyncio.run(self.repo.update(memory.id, update_data))
        
        self.assertIsNotNone(updated)
        self.assertEqual(updated.content, "Updated content")
        
        # Verify persistence
        retrieved = asyncio.run(self.repo.get_by_id(memory.id))
        self.assertEqual(retrieved.content, "Updated content")

    def test_delete(self) -> None:
        """Test deleting a memory."""
        # Create memory
        data = MockMemoryCreate(
            content="To be deleted",
            domain="build",
            entity_type="Test",
            match_key="delete-test",
        )
        memory = asyncio.run(self.repo.create(data))
        
        # Delete
        deleted = asyncio.run(self.repo.delete(memory.id))
        self.assertTrue(deleted)
        
        # Verify deletion
        retrieved = asyncio.run(self.repo.get_by_id(memory.id))
        self.assertIsNone(retrieved)
        
        # Deleting non-existent returns False
        deleted_again = asyncio.run(self.repo.delete(memory.id))
        self.assertFalse(deleted_again)

    def test_pagination(self) -> None:
        """Test list pagination."""
        # Create 5 memories
        for i in range(5):
            data = MockMemoryCreate(
                content=f"Content {i}",
                domain="build",
                entity_type="Test",
                match_key=f"page-key-{i}",
            )
            asyncio.run(self.repo.create(data))
        
        # Test pagination
        page1 = asyncio.run(self.repo.list_all(skip=0, limit=2))
        self.assertEqual(len(page1), 2)
        
        page2 = asyncio.run(self.repo.list_all(skip=2, limit=2))
        self.assertEqual(len(page2), 2)
        
        page3 = asyncio.run(self.repo.list_all(skip=4, limit=2))
        self.assertEqual(len(page3), 1)

    def test_clear_and_seed(self) -> None:
        """Test clear and seed helpers."""
        # Create memories
        for i in range(3):
            data = MockMemoryCreate(
                content=f"Content {i}",
                domain="build",
                entity_type="Test",
                match_key=f"seed-key-{i}",
            )
            asyncio.run(self.repo.create(data))
        
        self.assertEqual(asyncio.run(self.repo.count()), 3)
        
        # Clear
        self.repo.clear()
        self.assertEqual(asyncio.run(self.repo.count()), 0)
        
        # Seed
        memory = Memory(
            id="mem_100",
            content="Seeded memory",
            domain="build",
            entity_type="Test",
            match_key="seeded-key",
        )
        self.repo.seed([memory])
        
        retrieved = asyncio.run(self.repo.get_by_id("mem_100"))
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.content, "Seeded memory")

    def test_search_by_embedding_filters_non_active_records(self) -> None:
        active = Memory(
            id="mem_1",
            content="Active memory",
            domain="build",
            entity_type="Test",
            match_key="active-key",
            status="active",
            embedding=[1.0, 0.0],
        )
        superseded = Memory(
            id="mem_2",
            content="Superseded memory",
            domain="build",
            entity_type="Test",
            match_key="superseded-key",
            status="superseded",
            embedding=[1.0, 0.0],
        )
        self.repo.seed([active, superseded])

        results = asyncio.run(
            self.repo.search_by_embedding([1.0, 0.0], top_k=5, threshold=0.0)
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].id, "mem_1")


class TestSQLAlchemyMemoryRepositorySearchPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_search_by_embedding_filters_to_active_records_only(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from src.repositories import SQLAlchemyMemoryRepository

        captured_stmt = None

        async def execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return SimpleNamespace(all=lambda: [])

        session = AsyncMock()
        session.execute.side_effect = execute
        repo = SQLAlchemyMemoryRepository(session)

        await repo.search_by_embedding([1.0, 0.0], top_k=3)

        self.assertIsNotNone(captured_stmt)
        stmt_text = str(captured_stmt)
        self.assertIn("memories.status", stmt_text)
        self.assertIn("= :status_1", stmt_text)


class TestRepositoryFactory(unittest.TestCase):
    """Tests for repository factory function."""

    def test_get_repository_returns_sqlalchemy(self) -> None:
        """Test that get_repository returns SQLAlchemy implementation."""
        from unittest.mock import AsyncMock
        from src.memory_reads import get_repository
        from src.repositories import SQLAlchemyMemoryRepository
        
        mock_session = AsyncMock()
        repo = get_repository(mock_session)
        
        self.assertIsInstance(repo, SQLAlchemyMemoryRepository)


if __name__ == "__main__":
    unittest.main()
