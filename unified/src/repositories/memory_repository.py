"""
Repository Pattern implementation for Memory data access (ARCH-002).

This module provides an abstraction layer between business logic and data storage,
enabling easier testing and future database migrations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Memory
from ..schemas import MemoryCreate, MemoryUpdate


class MemoryRepository(ABC):
    """
    Abstract base class for Memory data access.
    
    This repository provides a clean interface for CRUD operations on Memory entities,
    decoupling business logic from database implementation details.
    
    Implementations:
        - SQLAlchemyMemoryRepository: Production implementation using PostgreSQL
        - InMemoryMemoryRepository: Test implementation using in-memory storage
    """

    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> Memory | None:
        """Retrieve a memory by its unique identifier."""
        ...

    @abstractmethod
    async def get_by_match_key(self, match_key: str) -> Memory | None:
        """Retrieve a memory by its match key (idempotency)."""
        ...

    @abstractmethod
    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> list[Memory]:
        """List memories with optional filtering and pagination."""
        ...

    @abstractmethod
    async def count(
        self,
        *,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count memories matching the given filters."""
        ...

    # -------------------------------------------------------------------------
    # Write Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def create(self, data: MemoryCreate) -> Memory:
        """Create a new memory record."""
        ...

    @abstractmethod
    async def update(self, memory_id: str, data: MemoryUpdate) -> Memory | None:
        """Update an existing memory record."""
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted, False if not found."""
        ...

    # -------------------------------------------------------------------------
    # Specialized Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def search_by_embedding(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """
        Search memories by vector similarity.
        
        Returns list of (memory, similarity_score) tuples sorted by similarity.
        """
        ...


class SQLAlchemyMemoryRepository(MemoryRepository):
    """
    SQLAlchemy-based implementation of MemoryRepository.
    
    Uses async SQLAlchemy 2.0 patterns for optimal performance with PostgreSQL.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, memory_id: str) -> Memory | None:
        stmt = select(Memory).where(Memory.id == memory_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_match_key(self, match_key: str) -> Memory | None:
        stmt = select(Memory).where(Memory.match_key == match_key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> list[Memory]:
        stmt = select(Memory)
        
        if domain:
            stmt = stmt.where(Memory.domain == domain)
        if entity_type:
            stmt = stmt.where(Memory.entity_type == entity_type)
        if status:
            stmt = stmt.where(Memory.status == status)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Memory)
        
        if domain:
            stmt = stmt.where(Memory.domain == domain)
        if entity_type:
            stmt = stmt.where(Memory.entity_type == entity_type)
        if status:
            stmt = stmt.where(Memory.status == status)
        
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def create(self, data: MemoryCreate) -> Memory:
        memory = Memory(**data.model_dump(exclude_unset=True))
        self._session.add(memory)
        await self._session.flush()  # Get the ID without committing
        await self._session.refresh(memory)
        return memory

    async def update(self, memory_id: str, data: MemoryUpdate) -> Memory | None:
        memory = await self.get_by_id(memory_id)
        if memory is None:
            return None
        
        update_data = data.model_dump(exclude_unset=True, exclude_defaults=True)
        for key, value in update_data.items():
            setattr(memory, key, value)
        
        await self._session.flush()
        await self._session.refresh(memory)
        return memory

    async def delete(self, memory_id: str) -> bool:
        memory = await self.get_by_id(memory_id)
        if memory is None:
            return False
        
        await self._session.delete(memory)
        await self._session.flush()
        return True

    async def search_by_embedding(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """
        Search using pgvector cosine similarity.
        
        Note: This requires the vector extension and proper index.
        """
        # Use pgvector's <=> operator for cosine distance
        # Cosine similarity = 1 - cosine distance
        stmt = (
            select(Memory, (1 - Memory.embedding.cosine_distance(embedding)).label("similarity"))
            .where(Memory.embedding.isnot(None))
            .order_by(Memory.embedding.cosine_distance(embedding))
            .limit(top_k)
        )
        
        result = await self._session.execute(stmt)
        rows = result.all()
        
        # Filter by threshold
        return [(row[0], float(row[1])) for row in rows if float(row[1]) >= threshold]


class InMemoryMemoryRepository(MemoryRepository):
    """
    In-memory implementation of MemoryRepository for testing.
    
    This implementation stores data in Python dictionaries and provides
    deterministic behavior for unit tests without database dependencies.
    """

    def __init__(self):
        self._storage: dict[str, Memory] = {}
        self._match_key_index: dict[str, str] = {}  # match_key -> memory_id
        self._id_counter = 0

    async def get_by_id(self, memory_id: str) -> Memory | None:
        return self._storage.get(memory_id)

    async def get_by_match_key(self, match_key: str) -> Memory | None:
        memory_id = self._match_key_index.get(match_key)
        if memory_id:
            return self._storage.get(memory_id)
        return None

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> list[Memory]:
        memories = list(self._storage.values())
        
        if domain:
            memories = [m for m in memories if m.domain == domain]
        if entity_type:
            memories = [m for m in memories if m.entity_type == entity_type]
        if status:
            memories = [m for m in memories if m.status == status]
        
        return memories[skip:skip + limit]

    async def count(
        self,
        *,
        domain: str | None = None,
        entity_type: str | None = None,
        status: str | None = None,
    ) -> int:
        memories = list(self._storage.values())
        
        if domain:
            memories = [m for m in memories if m.domain == domain]
        if entity_type:
            memories = [m for m in memories if m.entity_type == entity_type]
        if status:
            memories = [m for m in memories if m.status == status]
        
        return len(memories)

    async def create(self, data: MemoryCreate) -> Memory:
        self._id_counter += 1
        memory_id = f"mem_{self._id_counter}"
        
        # Create memory object
        memory_data = data.model_dump(exclude_unset=True)
        memory_data["id"] = memory_id
        memory = Memory(**memory_data)
        
        self._storage[memory_id] = memory
        if memory.match_key:
            self._match_key_index[memory.match_key] = memory_id
        
        return memory

    async def update(self, memory_id: str, data: MemoryUpdate) -> Memory | None:
        memory = self._storage.get(memory_id)
        if memory is None:
            return None
        
        update_data = data.model_dump(exclude_unset=True, exclude_defaults=True)
        
        # Handle match_key index update
        if "match_key" in update_data and update_data["match_key"] != memory.match_key:
            if memory.match_key:
                del self._match_key_index[memory.match_key]
            if update_data["match_key"]:
                self._match_key_index[update_data["match_key"]] = memory_id
        
        for key, value in update_data.items():
            setattr(memory, key, value)
        
        return memory

    async def delete(self, memory_id: str) -> bool:
        memory = self._storage.pop(memory_id, None)
        if memory is None:
            return False
        
        if memory.match_key:
            del self._match_key_index[memory.match_key]
        
        return True

    async def search_by_embedding(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """
        Simplified vector search for in-memory implementation.
        
        Uses dot product as similarity metric (not cosine, for simplicity in tests).
        """
        import numpy as np
        
        if not embedding:
            return []
        
        query_vec = np.array(embedding)
        results = []
        
        for memory in self._storage.values():
            if memory.embedding is None:
                continue
            
            mem_vec = np.array(memory.embedding)
            # Normalize for cosine similarity approximation
            query_norm = np.linalg.norm(query_vec)
            mem_norm = np.linalg.norm(mem_vec)
            
            if query_norm == 0 or mem_norm == 0:
                continue
            
            similarity = float(np.dot(query_vec, mem_vec) / (query_norm * mem_norm))
            
            if similarity >= threshold:
                results.append((memory, similarity))
        
        # Sort by similarity descending and take top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # Test helpers
    def clear(self) -> None:
        """Clear all stored memories (test helper)."""
        self._storage.clear()
        self._match_key_index.clear()
        self._id_counter = 0

    def seed(self, memories: list[Memory]) -> None:
        """Seed repository with test data."""
        for memory in memories:
            self._storage[memory.id] = memory
            if memory.match_key:
                self._match_key_index[memory.match_key] = memory.id
            # Update counter to be higher than any existing ID
            if memory.id.startswith("mem_"):
                try:
                    num = int(memory.id.split("_")[1])
                    self._id_counter = max(self._id_counter, num)
                except (IndexError, ValueError):
                    pass
