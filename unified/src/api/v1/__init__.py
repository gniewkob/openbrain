"""V1 API endpoints."""

from .health import router as health_router
from .memory import router as memory_router
from .obsidian import router as obsidian_router

__all__ = [
    "health_router",
    "memory_router",
    "obsidian_router",
]
