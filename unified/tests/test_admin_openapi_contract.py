from __future__ import annotations

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(monkeypatch) -> TestClient:
    from src import auth, config

    monkeypatch.setenv("PUBLIC_MODE", "false")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    config.get_config.cache_clear()
    import importlib

    importlib.reload(auth)

    from src.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_admin_report_query_bounds_contract(client: TestClient) -> None:
    response = client.get("/openapi.json")
    data = response.json()
    get_op = data["paths"]["/api/v1/memory/admin/test-data/report"]["get"]
    parameters = get_op.get("parameters", [])
    sample_param = next(
        (item for item in parameters if item.get("name") == "sample_limit"),
        {},
    )
    schema = sample_param.get("schema", {})

    assert schema.get("default") == 20
    assert schema.get("minimum") == 1
    assert schema.get("maximum") == 100


def test_admin_cleanup_request_bounds_contract(client: TestClient) -> None:
    response = client.get("/openapi.json")
    data = response.json()
    schemas = data.get("components", {}).get("schemas", {})
    request_schema = schemas.get("BuildTestDataCleanupRequest", {})
    properties = request_schema.get("properties", {})
    limit_schema = properties.get("limit", {})
    dry_run_schema = properties.get("dry_run", {})

    assert limit_schema.get("default") == 100
    assert limit_schema.get("minimum") == 1
    assert limit_schema.get("maximum") == 500
    assert dry_run_schema.get("default") is True


def test_admin_cleanup_response_shape_contract(client: TestClient) -> None:
    response = client.get("/openapi.json")
    data = response.json()
    schemas = data.get("components", {}).get("schemas", {})
    cleanup_schema = schemas.get("BuildTestDataCleanupResponse", {})
    properties = cleanup_schema.get("properties", {})

    assert "dry_run" in properties
    assert "scanned" in properties
    assert "candidates_count" in properties
    assert "deleted_count" in properties
    assert "skipped_count" in properties
    assert "candidate_ids" in properties
    assert "deleted_ids" in properties
    assert "skipped" in properties
