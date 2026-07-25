from __future__ import annotations


def test_health_routes_are_exposed_on_root_and_v1_prefix() -> None:
    from src.main import app

    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif "IncludedRouter" in type(route).__name__:
            prefix = (
                getattr(route, "include_context", None)
                and getattr(route.include_context, "prefix", "")
                or ""
            )
            for r in getattr(route.original_router, "routes", []):
                if hasattr(r, "path"):
                    paths.add(prefix + r.path)

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
