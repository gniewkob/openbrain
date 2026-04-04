"""
Repository Pattern implementation for OpenBrain.

Provides abstraction layer for data access, making testing and maintenance easier.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .models import Memory


class MemoryRepository(ABC):
    """
    Abstract repository for Memory entity.
    
    Defines the interface for memory data access.
    Implementations: SQLAlchemyMemoryRepository, InMemoryMemoryRepository (for testing)
    """
    
    @abstractmethod
    async def get_by_id(self, memory_id: str) -> Optional["Memory"]:
        """Get memory by ID."""
        pass
    
    @abstractmethod
    async def get_by_match_key(self, match_key: str, status: str = "active") -> Optional["Memory"]:
        """Get memory by match_key."""
        pass
    
    @abstractmethod
    async def list_all(
        self,
        filters: dict[str, Any],
        limit: int = 20,
        offset: int = 0,
    ) -> list["Memory"]:
        """List memories with filters."""
        pass
    
    @abstractmethod
    async def create(self, memory: "Memory") -> "Memory":
        """Create new memory."""
        pass
    
    @abstractmethod
    async def update(self, memory: "Memory") -> "Memory":
        """Update existing memory."""
        pass
    
    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete memory (hard or soft)."""
        pass
    
    @abstractmethod
    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count memories matching filters."""
        pass
    
    @abstractmethod
    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple["Memory", float]]:
        """Semantic search using vector similarity."""
        pass
    
    @abstractmethod
    async def get_by_obsidian_ref(self, obsidian_ref: str) -> Optional["Memory"]:
        """Get memory by Obsidian reference."""
        pass
    
    @abstractmethod
    async def list_by_domain(
        self,
        domain: str,
        limit: int = 100,
    ) -> list["Memory"]:
        """List memories by domain."""
        pass


class SQLAlchemyMemoryRepository(MemoryRepository):
    """
    SQLAlchemy implementation of MemoryRepository.
    
    Uses async SQLAlchemy for database operations.
    """
    
    def __init__(self, session: "AsyncSession"):
        self.session = session
    
    async def get_by_id(self, memory_id: str) -> Optional["Memory"]:
        """Get memory by ID."""
        from sqlalchemy import select
        from .models import Memory
        
        stmt = select(Memory).where(Memory.id == memory_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_match_key(self, match_key: str, status: str = "active") -> Optional["Memory"]:
        """Get memory by match_key."""
        from sqlalchemy import select
        from .models import Memory
        
        stmt = (
            select(Memory)
            .where(Memory.match_key == match_key, Memory.status == status)
            .order_by(Memory.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_all(
        self,
        filters: dict[str, Any],
        limit: int = 20,
        offset: int = 0,
    ) -> list["Memory"]:
        """List memories with filters."""
        from sqlalchemy import select
        from .models import Memory, DomainEnum
        from .crud_common import STATUS_SUPERSEDED, STATUS_DUPLICATE, _tenant_filter_expr
        
        stmt = select(Memory)
        
        # Apply filters using the common filter function
        if "domain" in filters:
            domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
            stmt = stmt.where(Memory.domain.in_([DomainEnum(d) for d in domains]))
        
        if "entity_type" in filters:
            entity_types = filters["entity_type"]
            if isinstance(entity_types, list):
                stmt = stmt.where(Memory.entity_type.in_(entity_types))
            else:
                stmt = stmt.where(Memory.entity_type == entity_types)
        
        if "status" in filters:
            stmt = stmt.where(Memory.status == filters["status"])
        else:
            stmt = stmt.where(Memory.status.notin_([STATUS_SUPERSEDED, STATUS_DUPLICATE]))
        
        if "sensitivity" in filters:
            stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
        
        if "owner" in filters:
            owners = filters["owner"]
            if isinstance(owners, list):
                stmt = stmt.where(Memory.owner.in_(owners))
            else:
                stmt = stmt.where(Memory.owner == owners)
        
        if "tenant_id" in filters:
            tenant_ids = filters["tenant_id"]
            if isinstance(tenant_ids, list):
                stmt = stmt.where(_tenant_filter_expr(tenant_ids))
            else:
                stmt = stmt.where(_tenant_filter_expr([tenant_ids]))
        
        if "tags_any" in filters:
            stmt = stmt.where(Memory.tags.overlap(filters["tags_any"]))
        
        stmt = stmt.order_by(Memory.updated_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def create(self, memory: "Memory") -> "Memory":
        """Create new memory."""
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        return memory
    
    async def update(self, memory: "Memory") -> "Memory":
        """Update existing memory."""
        await self.session.flush()
        await self.session.refresh(memory)
        return memory
    
    async def delete(self, memory_id: str) -> bool:
        """Hard delete memory."""
        memory = await self.get_by_id(memory_id)
        if not memory:
            return False
        await self.session.delete(memory)
        return True
    
    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count memories matching filters."""
        from sqlalchemy import func, select
        from .models import Memory
        from .crud_common import STATUS_SUPERSEDED, STATUS_DUPLICATE
        
        filters = filters or {}
        stmt = select(func.count(Memory.id))
        
        if "status" in filters:
            stmt = stmt.where(Memory.status == filters["status"])
        else:
            stmt = stmt.where(Memory.status.notin_([STATUS_SUPERSEDED, STATUS_DUPLICATE]))
        
        if "domain" in filters:
            from .models import DomainEnum
            domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
            stmt = stmt.where(Memory.domain.in_([DomainEnum(d) for d in domains]))
        
        result = await self.session.execute(stmt)
        return result.scalar_one()
    
    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple["Memory", float]]:
        """Semantic search using vector similarity."""
        from sqlalchemy import select
        from .models import Memory, DomainEnum
        from .crud_common import _tenant_filter_expr
        
        filters = filters or {}
        
        stmt = (
            select(Memory, Memory.embedding.cosine_distance(embedding).label("distance"))
            .where(Memory.status == "active")
        )
        
        if "domain" in filters:
            domains = filters["domain"] if isinstance(filters["domain"], list) else [filters["domain"]]
            stmt = stmt.where(Memory.domain.in_([DomainEnum(d) for d in domains]))
        
        if "entity_type" in filters:
            stmt = stmt.where(Memory.entity_type == filters["entity_type"])
        
        if "sensitivity" in filters:
            stmt = stmt.where(Memory.sensitivity == filters["sensitivity"])
        
        if "tenant_id" in filters:
            stmt = stmt.where(_tenant_filter_expr([filters["tenant_id"]]))
        
        if "owner" in filters:
            stmt = stmt.where(Memory.owner == filters["owner"])
        
        stmt = stmt.order_by("distance").limit(top_k)
        result = await self.session.execute(stmt)
        
        return [(row.Memory, 1.0 - float(row.distance)) for row in result.all()]
    
    async def get_by_obsidian_ref(self, obsidian_ref: str) -> Optional["Memory"]:
        """Get memory by Obsidian reference."""
        from sqlalchemy import select
        from .models import Memory
        
        stmt = (
            select(Memory)
            .where(Memory.obsidian_ref == obsidian_ref, Memory.status == "active")
            .order_by(Memory.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_by_domain(self, domain: str, limit: int = 100) -> list["Memory"]:
        """List memories by domain."""
        from sqlalchemy import select
        from .models import Memory, DomainEnum
        from .crud_common import STATUS_SUPERSEDED, STATUS_DUPLICATE
        
        stmt = (
            select(Memory)
            .where(
                Memory.domain == DomainEnum(domain),
                Memory.status.notin_([STATUS_SUPERSEDED, STATUS_DUPLICATE])
            )
            .order_by(Memory.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class InMemoryMemoryRepository(MemoryRepository):
    """
    In-memory implementation for testing.
    
    Useful for unit tests without database.
    """
    
    def __init__(self):
        self._memories: dict[str, "Memory"] = {}
        self._id_counter = 0
    
    def _generate_id(self) -> str:
        """Generate unique ID."""
        self._id_counter += 1
        return f"mem_test_{self._id_counter}"
    
    async def get_by_id(self, memory_id: str) -> Optional["Memory"]:
        return self._memories.get(memory_id)
    
    async def get_by_match_key(self, match_key: str, status: str = "active") -> Optional["Memory"]:
        for memory in self._memories.values():
            if memory.match_key == match_key and memory.status == status:
                return memory
        return None
    
    async def list_all(
        self,
        filters: dict[str, Any],
        limit: int = 20,
        offset: int = 0,
    ) -> list["Memory"]:
        memories = list(self._memories.values())
        
        # Simple filtering
        if "domain" in filters:
            domain = filters["domain"]
            memories = [m for m in memories if m.domain.value == domain]
        
        if "status" in filters:
            status = filters["status"]
            memories = [m for m in memories if m.status == status]
        
        return memories[offset:offset + limit]
    
    async def create(self, memory: "Memory") -> "Memory":
        if not memory.id:
            memory.id = self._generate_id()
        self._memories[memory.id] = memory
        return memory
    
    async def update(self, memory: "Memory") -> "Memory":
        self._memories[memory.id] = memory
        return memory
    
    async def delete(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False
    
    async def count(self, filters: dict[str, Any] | None = None) -> int:
        return len(self._memories)
    
    async def search_by_embedding(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple["Memory", float]]:
        # Simplified - just return all with score 1.0
        memories = list(self._memories.values())[:top_k]
        return [(m, 1.0) for m in memories]
    
    async def get_by_obsidian_ref(self, obsidian_ref: str) -> Optional["Memory"]:
        for memory in self._memories.values():
            if memory.obsidian_ref == obsidian_ref:
                return memory
        return None
    
    async def list_by_domain(self, domain: str, limit: int = 100) -> list["Memory"]:
        memories = [
            m for m in self._memories.values()
            if m.domain.value == domain
        ]
        return memories[:limit]


# Repository factory for dependency injection
def get_memory_repository(session: "AsyncSession") -> MemoryRepository:
    """Factory function to create repository instance."""
    return SQLAlchemyMemoryRepository(session)
