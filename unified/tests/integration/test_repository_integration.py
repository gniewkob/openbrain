"""
Integration tests for Repository Pattern with PostgreSQL.

Requires Docker to be running.
Skip if Docker is not available.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import AsyncGenerator

# Skip early under unittest discover (SKIP_INTEGRATION_TESTS=1) or when
# testcontainers is not installed — both conditions indicate a CI environment
# that cannot run these pytest-fixture-based integration tests.
if os.environ.get("SKIP_INTEGRATION_TESTS") == "1":
    raise unittest.SkipTest("SKIP_INTEGRATION_TESTS is set")

try:
    from testcontainers.postgres import PostgresContainer
except ImportError as _exc:
    raise unittest.SkipTest("testcontainers not installed") from _exc

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Skip all integration tests if SKIP_INTEGRATION_TESTS is set
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="Integration tests skipped via SKIP_INTEGRATION_TESTS",
)

from src.models import Base, Memory
from src.repositories import SQLAlchemyMemoryRepository
from src.schemas import MemoryCreate, MemoryUpdate


@pytest_asyncio.fixture(scope="module")
async def postgres_url() -> AsyncGenerator[str, None]:
    """Provide PostgreSQL URL from testcontainer."""
    # Use existing database if DATABASE_URL is set (CI environment)
    if os.environ.get("INTEGRATION_TEST_DATABASE_URL"):
        yield os.environ["INTEGRATION_TEST_DATABASE_URL"]
        return

    # Otherwise start a testcontainer with pgvector
    postgres = PostgresContainer(
        "pgvector/pgvector:pg16",
        driver="asyncpg",
    )
    try:
        postgres.start()
        url = postgres.get_connection_url()
        yield url
    finally:
        postgres.stop()


@pytest_asyncio.fixture
async def db_session(postgres_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Provide database session with fresh schema."""
    # Create engine
    engine = create_async_engine(
        postgres_url,
        echo=False,
        pool_size=2,
        max_overflow=0,
    )

    # Create tables
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
class TestSQLAlchemyMemoryRepositoryIntegration:
    """Integration tests for SQLAlchemyMemoryRepository with real PostgreSQL."""

    async def test_create_and_get_by_id(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a memory."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create memory
        data = MemoryCreate(
            content="Test content",
            domain="build",
            entity_type="Test",
            match_key="test-key-1",
        )
        memory = await repo.create(data)

        assert memory.id is not None
        assert memory.content == "Test content"

        # Retrieve by ID
        retrieved = await repo.get_by_id(memory.id)
        assert retrieved is not None
        assert retrieved.id == memory.id
        assert retrieved.content == "Test content"

    async def test_get_by_match_key(self, db_session: AsyncSession) -> None:
        """Test retrieving by match_key."""
        repo = SQLAlchemyMemoryRepository(db_session)

        data = MemoryCreate(
            content="Test content",
            domain="build",
            entity_type="Test",
            match_key="unique-match-key",
        )
        memory = await repo.create(data)

        # Retrieve by match_key
        retrieved = await repo.get_by_match_key("unique-match-key")
        assert retrieved is not None
        assert retrieved.id == memory.id

    async def test_get_by_id_not_found(self, db_session: AsyncSession) -> None:
        """Test retrieving non-existent memory returns None."""
        repo = SQLAlchemyMemoryRepository(db_session)

        retrieved = await repo.get_by_id("non-existent-id")
        assert retrieved is None

    async def test_list_all_with_pagination(self, db_session: AsyncSession) -> None:
        """Test listing with pagination."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create test memories
        for i in range(5):
            data = MemoryCreate(
                content=f"Content {i}",
                domain="build",
                entity_type="Test",
                match_key=f"list-key-{i}",
            )
            await repo.create(data)

        # List all
        all_memories = await repo.list_all()
        assert len(all_memories) == 5

        # Pagination
        page1 = await repo.list_all(skip=0, limit=2)
        assert len(page1) == 2

        page2 = await repo.list_all(skip=2, limit=2)
        assert len(page2) == 2

        page3 = await repo.list_all(skip=4, limit=2)
        assert len(page3) == 1

    async def test_list_all_with_filters(self, db_session: AsyncSession) -> None:
        """Test listing with filters."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create test memories with different domains
        for i in range(4):
            data = MemoryCreate(
                content=f"Content {i}",
                domain="build" if i < 2 else "personal",
                entity_type="Test",
                match_key=f"filter-key-{i}",
                status="active" if i < 3 else "deprecated",
            )
            await repo.create(data)

        # Filter by domain
        build_memories = await repo.list_all(domain="build")
        assert len(build_memories) == 2

        # Filter by status
        active_memories = await repo.list_all(status="active")
        assert len(active_memories) == 3

        deprecated_memories = await repo.list_all(status="deprecated")
        assert len(deprecated_memories) == 1

        # Combined filters
        build_active = await repo.list_all(domain="build", status="active")
        assert len(build_active) == 2

    async def test_count(self, db_session: AsyncSession) -> None:
        """Test counting memories."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create test memories
        for i in range(5):
            data = MemoryCreate(
                content=f"Content {i}",
                domain="build" if i < 3 else "personal",
                entity_type="Test",
                match_key=f"count-key-{i}",
            )
            await repo.create(data)

        assert await repo.count() == 5
        assert await repo.count(domain="build") == 3
        assert await repo.count(domain="personal") == 2

    async def test_update(self, db_session: AsyncSession) -> None:
        """Test updating a memory."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create memory
        data = MemoryCreate(
            content="Original content",
            domain="build",
            entity_type="Test",
            match_key="update-test",
        )
        memory = await repo.create(data)

        # Update
        update_data = MemoryUpdate(content="Updated content")
        updated = await repo.update(memory.id, update_data)

        assert updated is not None
        assert updated.content == "Updated content"

        # Verify persistence
        retrieved = await repo.get_by_id(memory.id)
        assert retrieved.content == "Updated content"

    async def test_update_not_found(self, db_session: AsyncSession) -> None:
        """Test updating non-existent memory returns None."""
        repo = SQLAlchemyMemoryRepository(db_session)

        update_data = MemoryUpdate(content="Updated content")
        result = await repo.update("non-existent-id", update_data)

        assert result is None

    async def test_delete(self, db_session: AsyncSession) -> None:
        """Test deleting a memory."""
        repo = SQLAlchemyMemoryRepository(db_session)

        # Create memory
        data = MemoryCreate(
            content="To be deleted",
            domain="build",
            entity_type="Test",
            match_key="delete-test",
        )
        memory = await repo.create(data)

        # Delete
        deleted = await repo.delete(memory.id)
        assert deleted is True

        # Verify deletion
        retrieved = await repo.get_by_id(memory.id)
        assert retrieved is None

        # Deleting non-existent returns False
        deleted_again = await repo.delete(memory.id)
        assert deleted_again is False


# Run tests only if Docker is available
def setup_module():
    """Check if Docker is available before running tests."""
    import subprocess

    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available", allow_module_level=True)
