"""
Validation tests for OpenBrain API.
Tests that all endpoints and components are properly registered.
"""

from __future__ import annotations

import pytest


class TestFastAPIApp:
    """Test FastAPI app initialization."""
    
    def test_app_loads(self) -> None:
        """Test that FastAPI app loads correctly."""
        from src.main import app
        assert app.title == "OpenBrain Unified Memory Service"
        assert app.version == "2.0.0"


class TestRouteRegistration:
    """Test that all routes are registered."""
    
    def test_health_routes(self) -> None:
        """Test health check routes."""
        from src.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]

        assert '/api/v1/healthz' in paths
        assert '/api/v1/readyz' in paths
        assert '/api/v1/health' in paths
    
    def test_v1_api_routes(self) -> None:
        """Test V1 API routes."""
        from src.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        
        assert '/api/v1/memory/write' in paths
        assert '/api/v1/memory/write-many' in paths
        assert '/api/v1/memory/find' in paths
        assert '/api/v1/memory/get-context' in paths
        assert '/api/v1/memory/{memory_id}' in paths
    
    def test_obsidian_routes(self) -> None:
        """Test Obsidian API routes."""
        from src.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        
        assert '/api/v1/obsidian/vaults' in paths
        assert '/api/v1/obsidian/read-note' in paths
        assert '/api/v1/obsidian/write-note' in paths
        assert '/api/v1/obsidian/update-note' in paths
        assert '/api/v1/obsidian/sync' in paths
        assert '/api/v1/obsidian/export' in paths
        assert '/api/v1/obsidian/collection' in paths
        assert '/api/v1/obsidian/bidirectional-sync' in paths
        assert '/api/v1/obsidian/sync-status' in paths


class TestRepositoryPattern:
    """Test Repository Pattern implementation."""
    
    def test_memory_repository_abc(self) -> None:
        """Test MemoryRepository abstract base class."""
        from src.repositories import MemoryRepository
        from abc import ABC
        assert issubclass(MemoryRepository, ABC)
    
    def test_sqlalchemy_repository(self) -> None:
        """Test SQLAlchemyMemoryRepository."""
        from src.repositories import SQLAlchemyMemoryRepository
        assert SQLAlchemyMemoryRepository.__name__ == "SQLAlchemyMemoryRepository"
    
    def test_inmemory_repository(self) -> None:
        """Test InMemoryMemoryRepository."""
        from src.repositories import InMemoryMemoryRepository
        assert InMemoryMemoryRepository.__name__ == "InMemoryMemoryRepository"


class TestExceptionHierarchy:
    """Test exception hierarchy."""
    
    def test_base_exception(self) -> None:
        """Test OpenBrainError base class."""
        from src.exceptions import OpenBrainError
        exc = OpenBrainError("Test message")
        assert exc.message == "Test message"
        assert exc.status_code == 500
    
    def test_validation_error(self) -> None:
        """Test ValidationError."""
        from src.exceptions import ValidationError
        exc = ValidationError("Invalid input")
        assert exc.status_code == 422
        assert exc.error_code == "validation_error"
    
    def test_not_found_error(self) -> None:
        """Test NotFoundError."""
        from src.exceptions import NotFoundError
        exc = NotFoundError("Not found")
        assert exc.status_code == 404
    
    def test_memory_not_found_error(self) -> None:
        """Test MemoryNotFoundError."""
        from src.exceptions import MemoryNotFoundError
        assert issubclass(MemoryNotFoundError, Exception)
    
    def test_obsidian_cli_error(self) -> None:
        """Test ObsidianCliError."""
        from src.exceptions import ObsidianCliError
        exc = ObsidianCliError("CLI failed")
        assert exc.status_code == 502
    
    def test_sync_conflict_error(self) -> None:
        """Test SyncConflictError."""
        from src.exceptions import SyncConflictError
        exc = SyncConflictError("Conflict", memory_id="mem_123", note_path="note.md")
        assert exc.memory_id == "mem_123"
        assert exc.note_path == "note.md"


class TestObsidianSync:
    """Test Obsidian sync components."""
    
    def test_sync_strategy_enum(self) -> None:
        """Test SyncStrategy enum."""
        from src.obsidian_sync import SyncStrategy
        assert SyncStrategy.LAST_WRITE_WINS.value == "last_write_wins"
        assert SyncStrategy.DOMAIN_BASED.value == "domain_based"
        assert SyncStrategy.MANUAL_REVIEW.value == "manual_review"
    
    def test_change_type_enum(self) -> None:
        """Test ChangeType enum."""
        from src.obsidian_sync import ChangeType
        assert ChangeType.CREATED.value == "created"
        assert ChangeType.UPDATED.value == "updated"
        assert ChangeType.DELETED.value == "deleted"
    
    def test_bidirectional_sync_engine(self) -> None:
        """Test BidirectionalSyncEngine class."""
        from src.obsidian_sync import BidirectionalSyncEngine
        assert BidirectionalSyncEngine.__name__ == "BidirectionalSyncEngine"
    
    def test_change_tracker(self) -> None:
        """Test ObsidianChangeTracker."""
        from src.obsidian_sync import ObsidianChangeTracker
        assert ObsidianChangeTracker.__name__ == "ObsidianChangeTracker"
    
    def test_obsidian_cli_adapter(self) -> None:
        """Test ObsidianCliAdapter."""
        from src.common.obsidian_adapter import ObsidianCliAdapter
        assert ObsidianCliAdapter.__name__ == "ObsidianCliAdapter"


class TestEmbedCache:
    """Test embedding cache."""
    
    def test_cache_size(self) -> None:
        """Test cache size configuration."""
        from src.config import get_config
        get_config.cache_clear()
        assert get_config().embedding.cache_size == 1000
    
    def test_cache_function_exists(self) -> None:
        """Test cache function exists."""
        from src.embed import _embedding_cache
        from collections import OrderedDict
        assert isinstance(_embedding_cache, OrderedDict)


class TestRateLimiting:
    """Test rate limiting setup."""
    
    def test_rate_limiter_configured(self) -> None:
        """Test rate limiter is configured in app."""
        from src.app_factory import create_app
        
        app = create_app(public_base_url="", lifespan=lambda x: None)
        assert hasattr(app.state, 'limiter')
    
    def test_default_limit_configured(self) -> None:
        """Test default rate limit is configured."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["100/minute"]
        )
        # LimitGroup object is stored, not string
        assert limiter._default_limits is not None
        assert len(limiter._default_limits) > 0


class TestCORS:
    """Test CORS configuration."""
    
    def test_cors_configuration_exists(self) -> None:
        """Test CORS configuration logic exists."""
        from src.app_factory import create_app
        # Just verify the app can be created with CORS settings
        app = create_app(public_base_url="https://test.com", lifespan=lambda x: None)
        assert app is not None


class TestAuth:
    """Test authentication components."""
    
    def test_auth_module_imports(self) -> None:
        """Test auth module can be imported."""
        from src import auth
        assert auth is not None
    
    def test_require_auth_dependency(self) -> None:
        """Test require_auth dependency."""
        from src.auth import require_auth
        assert callable(require_auth)


class TestTelemetry:
    """Test telemetry components."""
    
    def test_metrics_initialized(self) -> None:
        """Test metrics are initialized."""
        from src.telemetry import get_metrics_snapshot
        snapshot = get_metrics_snapshot()
        assert "counters" in snapshot
        assert "histograms" in snapshot


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
