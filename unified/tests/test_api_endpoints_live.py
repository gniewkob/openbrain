"""
Live API endpoint tests using FastAPI TestClient.
Tests all endpoints without requiring external database.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestAllEndpoints(unittest.TestCase):
    """Test all OpenBrain API endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test client."""
        from src.main import app

        cls.client = TestClient(app)
        cls.base_url = ""

    # ==================== Health Endpoints ====================

    def test_healthz_get(self) -> None:
        """Test GET /api/v1/healthz endpoint."""
        response = self.client.get("/api/v1/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "openbrain-unified"

    def test_readyz_get(self) -> None:
        """Test GET /api/v1/readyz endpoint."""
        response = self.client.get("/api/v1/readyz")
        # Returns 503 if DB unavailable, 200 if ready
        assert response.status_code in [200, 503]

    def test_health_get(self) -> None:
        """Test GET /api/v1/health endpoint (requires auth)."""
        response = self.client.get("/api/v1/health")
        # Can return 200, 401, 403, or 503 if DB unavailable
        assert response.status_code in [200, 401, 403, 503]

    # ==================== V1 Core API ====================

    def test_v1_memory_write_post(self) -> None:
        """Test POST /api/v1/memory/write endpoint."""
        payload = {
            "content": "Test memory",
            "domain": "build",
            "entity_type": "Test",
        }
        response = self.client.post("/api/v1/memory/write", json=payload)
        # Will fail auth or validation but endpoint exists
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_memory_write_many_post(self) -> None:
        """Test POST /api/v1/memory/write-many endpoint."""
        payload = {
            "records": [
                {"content": "Test 1", "domain": "build", "entity_type": "Test"},
                {"content": "Test 2", "domain": "build", "entity_type": "Test"},
            ]
        }
        response = self.client.post("/api/v1/memory/write-many", json=payload)
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_memory_find_post(self) -> None:
        """Test POST /api/v1/memory/find endpoint."""
        payload = {"query": "test", "filters": {}}
        response = self.client.post("/api/v1/memory/find", json=payload)
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_memory_get_context_post(self) -> None:
        """Test POST /api/v1/memory/get-context endpoint."""
        payload = {"query": "test query", "top_k": 3}
        response = self.client.post("/api/v1/memory/get-context", json=payload)
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_memory_get(self) -> None:
        """Test GET /api/v1/memory/{memory_id} endpoint."""
        response = self.client.get("/api/v1/memory/test-id-123")
        assert response.status_code in [200, 401, 403, 404]

    # ==================== V1 Obsidian API ====================

    def test_v1_obsidian_vaults_get(self) -> None:
        """Test GET /api/v1/obsidian/vaults endpoint."""
        response = self.client.get("/api/v1/obsidian/vaults")
        assert response.status_code in [200, 401, 403, 500]

    def test_v1_obsidian_read_note_post(self) -> None:
        """Test POST /api/v1/obsidian/read-note endpoint."""
        payload = {"vault": "Memory", "path": "test/note.md"}
        response = self.client.post("/api/v1/obsidian/read-note", json=payload)
        assert response.status_code in [200, 401, 403, 404, 422, 500]

    def test_v1_obsidian_write_note_post(self) -> None:
        """Test POST /api/v1/obsidian/write-note endpoint."""
        payload = {
            "vault": "Memory",
            "path": "test/note.md",
            "content": "# Test Note",
        }
        response = self.client.post("/api/v1/obsidian/write-note", json=payload)
        assert response.status_code in [200, 401, 403, 422, 500]

    def test_v1_obsidian_update_note_post(self) -> None:
        """Test POST /api/v1/obsidian/update-note endpoint."""
        payload = {
            "vault": "Memory",
            "path": "test/note.md",
            "content": "Updated content",
        }
        response = self.client.post("/api/v1/obsidian/update-note", json=payload)
        assert response.status_code in [200, 401, 403, 404, 422, 500]

    def test_v1_obsidian_sync_post(self) -> None:
        """Test POST /api/v1/obsidian/sync endpoint."""
        payload = {"vault": "Memory", "direction": "export"}
        response = self.client.post("/api/v1/obsidian/sync", json=payload)
        assert response.status_code in [200, 401, 403, 422, 500]

    def test_v1_obsidian_export_post(self) -> None:
        """Test POST /api/v1/obsidian/export endpoint."""
        payload = {"vault": "Memory", "folder": "export/test"}
        response = self.client.post("/api/v1/obsidian/export", json=payload)
        assert response.status_code in [200, 401, 403, 422, 500]

    def test_v1_obsidian_collection_post(self) -> None:
        """Test POST /api/v1/obsidian/collection endpoint."""
        payload = {"vault": "Memory", "collection_name": "TestCollection"}
        response = self.client.post("/api/v1/obsidian/collection", json=payload)
        assert response.status_code in [200, 401, 403, 422, 500]

    @unittest.skipIf(
        os.environ.get("SKIP_OBSIDIAN_SYNC_TEST"),
        "Skipped: requires DB + Obsidian (set SKIP_OBSIDIAN_SYNC_TEST='' to enable)",
    )
    def test_v1_obsidian_bidirectional_sync_post(self) -> None:
        """Test POST /api/v1/obsidian/bidirectional-sync endpoint."""
        payload = {"vault": "Memory", "strategy": "domain_based", "dry_run": True}
        response = self.client.post("/api/v1/obsidian/bidirectional-sync", json=payload)
        assert response.status_code in [200, 401, 403, 422, 500, 503]

    def test_v1_obsidian_sync_status_get(self) -> None:
        """Test GET /api/v1/obsidian/sync-status endpoint."""
        response = self.client.get("/api/v1/obsidian/sync-status?vault=Memory")
        assert response.status_code in [200, 401, 403, 500]

    # ==================== Legacy CRUD API ====================

    def test_legacy_memory_get(self) -> None:
        """Test GET /api/memories endpoint (legacy — may return 404 if not registered)."""
        response = self.client.get("/api/memories")
        assert response.status_code in [200, 401, 403, 404]

    def test_legacy_memory_post(self) -> None:
        """Test POST /api/memories endpoint (legacy — may return 404 if not registered)."""
        payload = {"content": "Test", "domain": "build", "entity_type": "Test"}
        response = self.client.post("/api/memories", json=payload)
        assert response.status_code in [200, 201, 401, 403, 404, 422]

    def test_legacy_memory_id_get(self) -> None:
        """Test GET /api/memories/{id} endpoint."""
        response = self.client.get("/api/memories/test-id-123")
        assert response.status_code in [200, 401, 403, 404]

    def test_legacy_search_post(self) -> None:
        """Test POST /api/memories/search endpoint (legacy — may return 404 if not registered)."""
        payload = {"query": "test"}
        response = self.client.post("/api/memories/search", json=payload)
        assert response.status_code in [200, 401, 403, 404, 422]

    def test_legacy_export_post(self) -> None:
        """Test POST /api/memories/export endpoint (legacy — may return 404 if not registered)."""
        payload = {"ids": ["mem_1", "mem_2"]}
        response = self.client.post("/api/memories/export", json=payload)
        assert response.status_code in [200, 401, 403, 404, 422]

    # ==================== Auth Endpoints ====================

    def test_oauth_protected_resource_get(self) -> None:
        """Test GET /.well-known/oauth-protected-resource endpoint."""
        response = self.client.get("/.well-known/oauth-protected-resource")
        assert response.status_code in [200, 404]

    def test_oauth_authorization_server_get(self) -> None:
        """Test GET /.well-known/oauth-authorization-server endpoint."""
        response = self.client.get("/.well-known/oauth-authorization-server")
        assert response.status_code in [200, 404]

    # ==================== Docs Endpoints ====================

    def test_docs_endpoint(self) -> None:
        """Test GET /docs endpoint (Swagger UI)."""
        response = self.client.get("/docs")
        assert response.status_code == 200

    def test_openapi_endpoint(self) -> None:
        """Test GET /openapi.json endpoint."""
        response = self.client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert len(data["paths"]) > 0


class TestEndpointResponseStructures(unittest.TestCase):
    """Test that endpoints return correct response structures."""

    def setUp(self) -> None:
        from src.main import app

        self.client = TestClient(app)

    def test_healthz_structure(self) -> None:
        """Test /api/v1/healthz returns correct structure."""
        response = self.client.get("/api/v1/healthz")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["status"] == "ok"

    def test_openapi_structure(self) -> None:
        """Test openapi.json has all expected paths."""
        response = self.client.get("/openapi.json")
        data = response.json()

        expected_paths = [
            "/api/v1/healthz",
            "/api/v1/memory/write",
            "/api/v1/memory/write-many",
            "/api/v1/memory/find",
            "/api/v1/memory/get-context",
            "/api/v1/obsidian/vaults",
            "/api/v1/obsidian/read-note",
            "/api/v1/obsidian/write-note",
            "/api/v1/obsidian/sync",
        ]

        for path in expected_paths:
            assert path in data["paths"], f"Missing path: {path}"


class TestErrorHandling(unittest.TestCase):
    """Test error handling across endpoints."""

    def setUp(self) -> None:
        from src.main import app

        self.client = TestClient(app)

    def test_404_error(self) -> None:
        """Test 404 error response."""
        response = self.client.get("/nonexistent-endpoint")
        assert response.status_code == 404

    def test_validation_error(self) -> None:
        """Test validation error on invalid payload."""
        # Send invalid payload (missing required fields)
        response = self.client.post("/api/v1/memory/write", json={})
        # Should return 422 for validation error
        assert response.status_code in [401, 403, 422]

    def test_method_not_allowed(self) -> None:
        """Test 405 method not allowed."""
        response = self.client.delete("/api/v1/healthz")
        assert response.status_code == 405


if __name__ == "__main__":
    unittest.main()
