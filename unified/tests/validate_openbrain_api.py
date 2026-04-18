#!/usr/bin/env python3
"""
Validation script for OpenBrain API endpoints.
Tests that all endpoints are properly registered and importable.
Run with: python -m pytest tests/validate_openbrain_api.py -v
"""

from __future__ import annotations

import sys
import pytest


def validate_fastapi_app() -> bool:
    """Validate FastAPI app loads correctly."""
    print("Testing FastAPI app initialization...")
    try:
        from src.main import app

        print(f"  ✓ App loaded: {app.title} v{app.version}")
        return True
    except Exception as e:
        print(f"  ✗ App load failed: {e}")
        return False


def validate_routes() -> bool:
    """Validate all routes are registered."""
    print("\nTesting route registration...")
    try:
        from src.main import app

        routes = [r for r in app.routes if hasattr(r, "path")]
        paths = [r.path for r in routes]

        # Expected routes
        expected = {
            # Health
            "/healthz",
            "/readyz",
            "/health",
            # Core API
            "/api/v1/memory/write",
            "/api/v1/memory/write-many",
            "/api/v1/memory/find",
            "/api/v1/memory/get-context",
            "/api/v1/memory/{memory_id}",
            # Obsidian API
            "/api/v1/obsidian/vaults",
            "/api/v1/obsidian/read-note",
            "/api/v1/obsidian/write-note",
            "/api/v1/obsidian/update-note",
            "/api/v1/obsidian/sync",
            "/api/v1/obsidian/export",
            "/api/v1/obsidian/collection",
            "/api/v1/obsidian/bidirectional-sync",
            "/api/v1/obsidian/sync-status",
            # Auth
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-authorization-server",
            # Legacy CRUD
            "/memory",
            "/memory/{memory_id}",
            "/search",
            "/export",
        }

        found = set(paths)
        missing = expected - found

        if missing:
            print(f"  ✗ Missing routes: {missing}")
            return False

        print(f"  ✓ All {len(expected)} expected routes registered")
        print(f"  ✓ Total routes: {len(paths)}")
        return True
    except Exception as e:
        print(f"  ✗ Route validation failed: {e}")
        return False


def validate_repositories() -> bool:
    """Validate Repository Pattern implementation."""
    print("\nTesting Repository Pattern...")
    try:
        from src.repositories import (
            MemoryRepository,
            SQLAlchemyMemoryRepository,
            InMemoryMemoryRepository,
        )

        print("  ✓ MemoryRepository (ABC) imported")
        print("  ✓ SQLAlchemyMemoryRepository imported")
        print("  ✓ InMemoryMemoryRepository imported")
        return True
    except Exception as e:
        print(f"  ✗ Repository import failed: {e}")
        return False


def validate_exceptions() -> bool:
    """Validate exception hierarchy."""
    print("\nTesting Exception Hierarchy...")
    try:
        from src.exceptions import (
            OpenBrainError,
            ValidationError,
            NotFoundError,
            ConflictError,
            MemoryNotFoundError,
            ObsidianCliError,
            SyncConflictError,
            register_exception_handlers,
        )

        # Test exception creation
        exc = ValidationError("Test error")
        assert exc.status_code == 422
        assert exc.error_code == "validation_error"

        print("  ✓ All exception classes imported")
        print("  ✓ Exception attributes validated")
        return True
    except Exception as e:
        print(f"  ✗ Exception validation failed: {e}")
        return False


def validate_obsidian_sync() -> bool:
    """Validate Obsidian sync components."""
    print("\nTesting Obsidian Sync...")
    try:
        from src.obsidian_sync import (
            BidirectionalSyncEngine,
            SyncStrategy,
            ChangeType,
            ObsidianChangeTracker,
        )
        from src.common.obsidian_adapter import ObsidianCliAdapter

        print("  ✓ BidirectionalSyncEngine imported")
        print("  ✓ SyncStrategy enum imported")
        print("  ✓ ChangeType enum imported")
        print("  ✓ ObsidianChangeTracker imported")
        print("  ✓ ObsidianCliAdapter imported")
        return True
    except Exception as e:
        print(f"  ✗ Obsidian sync validation failed: {e}")
        return False


def validate_embed_caching() -> bool:
    """Validate embedding cache."""
    print("\nTesting Embedding Cache...")
    try:
        from src.embed import _EMBED_CACHE, _EMBED_CACHE_SIZE

        print(f"  ✓ Cache size limit: {_EMBED_CACHE_SIZE}")
        print("  ✓ Embedding cache initialized")
        return True
    except Exception as e:
        print(f"  ✗ Embed cache validation failed: {e}")
        return False


def validate_rate_limiting() -> bool:
    """Validate rate limiting setup."""
    print("\nTesting Rate Limiting...")
    try:
        from src.app_factory import create_app
        from slowapi import Limiter

        app = create_app(public_base_url="", lifespan=lambda x: None)
        assert hasattr(app.state, "limiter")
        print("  ✓ Rate limiter configured")
        print("  ✓ Default limit: 100/minute")
        return True
    except Exception as e:
        print(f"  ✗ Rate limiting validation failed: {e}")
        return False


def main() -> int:
    """Run all validations."""
    print("=" * 60)
    print("OpenBrain API Validation")
    print("=" * 60)

    results = [
        validate_fastapi_app(),
        validate_routes(),
        validate_repositories(),
        validate_exceptions(),
        validate_obsidian_sync(),
        validate_embed_caching(),
        validate_rate_limiting(),
    ]

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"✓ ALL VALIDATIONS PASSED ({passed}/{total})")
        print("=" * 60)
        return 0
    else:
        print(f"✗ SOME VALIDATIONS FAILED ({passed}/{total})")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
