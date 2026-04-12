from __future__ import annotations


def test_health_routes_are_exposed_on_root_and_v1_prefix() -> None:
    from src.main import app

    paths = {route.path for route in app.routes}
    expected = {
        "/readyz",
        "/healthz",
        "/health",
        "/api/v1/readyz",
        "/api/v1/healthz",
        "/api/v1/health",
    }
    missing = sorted(expected - paths)
    assert not missing, f"Missing health route aliases: {missing}"
