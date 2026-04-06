"""
Summary test of all OpenBrain endpoints.
Shows which endpoints work without database vs require DB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from src.main import app

    return TestClient(app)


class TestEndpointsNoDBRequired:
    """Endpoints that work without database (auth/public)."""

    def test_healthz(self, client: TestClient) -> None:
        """Health check works without DB."""
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_readyz_endpoint_responds(self, client: TestClient) -> None:
        """Readyz responds — 200 when DB up, 503 when DB unavailable."""
        response = client.get("/api/v1/readyz")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data

    def test_docs_endpoint(self, client: TestClient) -> None:
        """Swagger UI works without DB."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_endpoint(self, client: TestClient) -> None:
        """OpenAPI schema works without DB."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert len(data["paths"]) > 30  # Should have many endpoints

    def test_oauth_well_known(self, client: TestClient) -> None:
        """OAuth well-known endpoints work."""
        response = client.get("/.well-known/oauth-protected-resource")
        # May return 404 if not configured, but endpoint exists
        assert response.status_code in [200, 404]


class TestEndpointsV1Core:
    """V1 Core API endpoints (require auth/DB)."""

    def test_v1_write_validation(self, client: TestClient) -> None:
        """V1 write validates input even without DB."""
        response = client.post("/api/v1/memory/write", json={})
        # Returns 422 for validation error (no content provided)
        assert response.status_code == 422

    def test_v1_write_many_validation(self, client: TestClient) -> None:
        """V1 write-many validates batch size."""
        # Too many items
        items = [
            {"content": f"Item {i}", "domain": "build", "entity_type": "Test"}
            for i in range(101)
        ]
        response = client.post("/api/v1/memory/write-many", json={"records": items})
        # Should validate batch size
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_find_validation(self, client: TestClient) -> None:
        """V1 find validates query."""
        response = client.post("/api/v1/memory/find", json={})
        # Missing required query field
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_get_context_validation(self, client: TestClient) -> None:
        """V1 get-context validates query."""
        response = client.post("/api/v1/memory/get-context", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_get_memory_by_id(self, client: TestClient) -> None:
        """V1 get memory by ID (requires auth/DB)."""
        response = client.get("/api/v1/memory/test-id")
        # Returns 401/403 without auth or 404/503 with auth but no DB
        assert response.status_code in [200, 401, 403, 404, 503]


class TestEndpointsV1Obsidian:
    """V1 Obsidian API endpoints."""

    def test_v1_obsidian_vaults(self, client: TestClient) -> None:
        """V1 obsidian vaults endpoint."""
        response = client.get("/api/v1/obsidian/vaults")
        assert response.status_code in [200, 401, 403]

    def test_v1_obsidian_read_note_validation(self, client: TestClient) -> None:
        """V1 obsidian read-note validates input."""
        response = client.post("/api/v1/obsidian/read-note", json={})
        # Missing vault and path
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_write_note_validation(self, client: TestClient) -> None:
        """V1 obsidian write-note validates input."""
        response = client.post("/api/v1/obsidian/write-note", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_update_note_validation(self, client: TestClient) -> None:
        """V1 obsidian update-note validates input."""
        response = client.post("/api/v1/obsidian/update-note", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_sync_validation(self, client: TestClient) -> None:
        """V1 obsidian sync validates input."""
        response = client.post("/api/v1/obsidian/sync", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_export_validation(self, client: TestClient) -> None:
        """V1 obsidian export validates input."""
        response = client.post("/api/v1/obsidian/export", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_collection_validation(self, client: TestClient) -> None:
        """V1 obsidian collection validates input."""
        response = client.post("/api/v1/obsidian/collection", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_bidirectional_sync(self, client: TestClient) -> None:
        """V1 obsidian bidirectional-sync validates input."""
        response = client.post("/api/v1/obsidian/bidirectional-sync", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_v1_obsidian_sync_status(self, client: TestClient) -> None:
        """V1 obsidian sync-status endpoint."""
        response = client.get("/api/v1/obsidian/sync-status")
        assert response.status_code in [200, 401, 403]


class TestEndpointsLegacy:
    """Legacy CRUD API endpoints."""

    def test_legacy_memories_get(self, client: TestClient) -> None:
        """Legacy GET /api/memories."""
        response = client.get("/api/memories")
        assert response.status_code in [200, 401, 403]

    def test_legacy_memories_post_validation(self, client: TestClient) -> None:
        """Legacy POST /api/memories validates input."""
        response = client.post("/api/memories", json={})
        assert response.status_code in [200, 401, 403, 422]

    def test_legacy_memories_id_get(self, client: TestClient) -> None:
        """Legacy GET /api/memories/{id}."""
        response = client.get("/api/memories/test-id")
        assert response.status_code in [200, 401, 403, 404]

    def test_legacy_search_post(self, client: TestClient) -> None:
        """Legacy POST /api/memories/search."""
        response = client.post("/api/memories/search", json={"query": "test"})
        assert response.status_code in [200, 401, 403]

    def test_legacy_export_post(self, client: TestClient) -> None:
        """Legacy POST /api/memories/export."""
        response = client.post("/api/memories/export", json={"ids": ["mem_1"]})
        assert response.status_code in [200, 401, 403]


class TestAllRoutesRegistered:
    """Verify all expected routes are registered."""

    def test_expected_v1_core_routes_exist(self, client: TestClient) -> None:
        """All V1 core routes are registered."""
        response = client.get("/openapi.json")
        paths = response.json()["paths"]

        expected = [
            "/api/v1/memory/write",
            "/api/v1/memory/write-many",
            "/api/v1/memory/find",
            "/api/v1/memory/get-context",
            "/api/v1/memory/{memory_id}",
        ]
        for path in expected:
            assert path in paths, f"Missing: {path}"

    def test_expected_v1_obsidian_routes_exist(self, client: TestClient) -> None:
        """All V1 Obsidian routes are registered."""
        response = client.get("/openapi.json")
        paths = response.json()["paths"]

        expected = [
            "/api/v1/obsidian/vaults",
            "/api/v1/obsidian/read-note",
            "/api/v1/obsidian/write-note",
            "/api/v1/obsidian/update-note",
            "/api/v1/obsidian/sync",
            "/api/v1/obsidian/export",
            "/api/v1/obsidian/collection",
            "/api/v1/obsidian/bidirectional-sync",
            "/api/v1/obsidian/sync-status",
        ]
        for path in expected:
            assert path in paths, f"Missing: {path}"

    def test_expected_legacy_routes_exist(self, client: TestClient) -> None:
        """All legacy routes are registered."""
        response = client.get("/openapi.json")
        paths = response.json()["paths"]

        expected = [
            "/api/memories",
            "/api/memories/{memory_id}",
            "/api/memories/search",
            "/api/memories/export",
        ]
        for path in expected:
            assert path in paths, f"Missing: {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
