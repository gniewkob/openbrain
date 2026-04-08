from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI

from src.app_factory import create_app
from src.routes_crud import register_crud_routes
from src.routes_ops import register_ops_routes
from src.routes_v1 import register_v1_routes


async def _handler(*args, **kwargs):
    return None


def _make_handlers(**overrides):
    names = {
        "healthz",
        "readyz",
        "health",
        "diagnostics_metrics",
        "prometheus_metrics",
        "create_memory",
        "create_memories_bulk",
        "bulk_upsert_memories",
        "read_memory",
        "read_memories",
        "search",
        "update",
        "delete",
        "check_sync_endpoint",
        "maintain",
        "read_policy_registry",
        "update_policy_registry",
        "maintain_reports",
        "maintain_report_detail",
        "export",
        "v1_write",
        "v1_write_many",
        "v1_find",
        "v1_get_context",
        "v1_get",
        "v1_obsidian_vaults",
        "v1_obsidian_read_note",
        "v1_obsidian_sync",
        "v1_obsidian_write_note",
        "v1_obsidian_export",
        "v1_obsidian_collection",
        "v1_obsidian_bidirectional_sync",
        "v1_obsidian_sync_status",
        "v1_obsidian_update_note",
        "oauth_protected_resource",
        "oauth_authorization_server",
    }
    mapping = {name: _handler for name in names}
    mapping.update(overrides)
    return types.SimpleNamespace(**mapping)


def _route_methods(app: FastAPI) -> dict[tuple[str, str], object]:
    routes = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes[(route.path, method)] = route
    return routes


class AppFactoryTests(unittest.TestCase):
    def test_create_app_sets_metadata_and_servers(self) -> None:
        async def _lifespan(app):
            yield

        with patch.dict("os.environ", {"PUBLIC_MODE": "false", "PUBLIC_BASE_URL": ""}):
            from src import config
            config.get_config.cache_clear()
            app = create_app(public_base_url="https://brain.example.com", lifespan=_lifespan)

        self.assertEqual(app.title, "OpenBrain Unified Memory Service")
        self.assertEqual(app.version, "2.0.0")
        self.assertEqual(app.docs_url, "/docs")
        self.assertIsNone(app.redoc_url)
        self.assertEqual(app.servers, [{"url": "https://brain.example.com"}])

    def test_create_app_omits_servers_when_base_url_missing(self) -> None:
        async def _lifespan(app):
            yield

        app = create_app(public_base_url="", lifespan=_lifespan)

        self.assertEqual(app.servers, [])


class RouteRegistrationTests(unittest.TestCase):
    def test_register_ops_routes_adds_expected_paths(self) -> None:
        app = FastAPI()
        register_ops_routes(app, _make_handlers())
        routes = _route_methods(app)

        for path in [
            ("/healthz", "GET"),
            ("/readyz", "GET"),
            ("/health", "GET"),
            ("/api/diagnostics/metrics", "GET"),
            ("/metrics", "GET"),
        ]:
            self.assertIn(path, routes)

    def test_register_v1_routes_adds_expected_paths(self) -> None:
        app = FastAPI()
        register_v1_routes(app, _make_handlers())
        routes = _route_methods(app)

        for path in [
            ("/api/v1/memory/write", "POST"),
            ("/api/v1/memory/write-many", "POST"),
            ("/api/v1/memory/find", "POST"),
            ("/api/v1/memory/get-context", "POST"),
            ("/api/v1/memory/{memory_id}", "GET"),
            ("/api/v1/obsidian/vaults", "GET"),
            ("/api/v1/obsidian/read-note", "POST"),
            ("/api/v1/obsidian/sync", "POST"),
            ("/.well-known/oauth-protected-resource", "GET"),
            ("/.well-known/oauth-authorization-server", "GET"),
        ]:
            self.assertIn(path, routes)

    def test_register_crud_routes_adds_expected_paths(self) -> None:
        app = FastAPI()
        register_crud_routes(app, _make_handlers())
        routes = _route_methods(app)

        for path in [
            ("/api/memories", "POST"),
            ("/api/memories/bulk", "POST"),
            ("/api/memories/bulk-upsert", "POST"),
            ("/api/memories/{memory_id}", "GET"),
            ("/api/memories", "GET"),
            ("/api/memories/search", "POST"),
            ("/api/memories/{memory_id}", "PUT"),
            ("/api/memories/{memory_id}", "DELETE"),
            ("/api/memories/sync-check", "POST"),
            ("/api/admin/maintain", "POST"),
            ("/api/admin/policy-registry", "GET"),
            ("/api/admin/policy-registry", "PUT"),
            ("/api/admin/maintain/reports", "GET"),
            ("/api/admin/maintain/reports/{report_id}", "GET"),
            ("/api/memories/export", "POST"),
        ]:
            self.assertIn(path, routes)


if __name__ == "__main__":
    unittest.main()
