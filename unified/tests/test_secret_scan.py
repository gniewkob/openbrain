"""Tests for secret scanning middleware and scanner logic."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests: _scan_for_secrets()
# ---------------------------------------------------------------------------


class TestScanForSecrets:
    """Unit tests for the scanner function (no HTTP, no app)."""

    def _scan(self, data: dict):
        from src.middleware import _scan_for_secrets

        return _scan_for_secrets(data)

    def test_clean_content_returns_false(self):
        found, pattern = self._scan(
            {"content": "This is a normal memory about projects."}
        )
        assert found is False
        assert pattern is None

    def test_openai_key_in_content_detected(self):
        found, pattern = self._scan(
            {"content": "my key is sk-abcdefghijklmnopqrstuvwxyz1234"}
        )
        assert found is True
        assert pattern == "openai_api_key"

    def test_github_token_in_content_detected(self):
        found, pattern = self._scan(
            {"content": "token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"}
        )
        assert found is True
        assert pattern == "github_token"

    def test_jwt_token_in_content_detected(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        found, pattern = self._scan({"content": f"Authorization header was: {jwt}"})
        assert found is True
        assert pattern == "jwt_token"

    def test_pem_private_key_in_content_detected(self):
        found, pattern = self._scan(
            {"content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."}
        )
        assert found is True
        assert pattern == "pem_private_key"

    def test_auth_url_in_content_detected(self):
        found, pattern = self._scan(
            {"content": "connect to https://admin:password123@db.example.com"}
        )
        assert found is True
        assert pattern == "auth_url"

    def test_inline_api_key_credential_detected(self):
        found, pattern = self._scan({"content": "api_key=supersecretvalue123"})
        assert found is True
        assert pattern == "inline_credential"

    def test_secret_in_custom_fields_detected(self):
        found, pattern = self._scan(
            {
                "content": "normal content",
                "custom_fields": {"config": "password=hunter2secret"},
            }
        )
        assert found is True
        assert pattern == "inline_credential"

    def test_nested_custom_fields_scanned(self):
        found, pattern = self._scan(
            {
                "content": "normal",
                "custom_fields": {
                    "level1": {"level2": "sk-abcdefghijklmnopqrstuvwxyz1234"}
                },
            }
        )
        assert found is True
        assert pattern == "openai_api_key"

    def test_missing_content_key_is_safe(self):
        """Payloads without 'content' key must not crash the scanner."""
        found, pattern = self._scan({"title": "just a title"})
        assert found is False

    def test_non_string_values_skipped(self):
        found, pattern = self._scan(
            {
                "content": "normal",
                "custom_fields": {"count": 42, "enabled": True, "items": [1, 2, 3]},
            }
        )
        assert found is False


# ---------------------------------------------------------------------------
# Integration tests: middleware blocks write endpoints
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_app():
    """Minimal FastAPI app with SecretScanMiddleware for integration tests."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from src.middleware import SecretScanMiddleware

    app = FastAPI()
    app.add_middleware(SecretScanMiddleware)

    @app.post("/api/v1/memory/write")
    async def write_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/memory/write-many")
    async def write_many_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.patch("/api/v1/memory/{memory_id}")
    async def patch_endpoint(memory_id: str, request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/memory/bulk-upsert")
    async def bulk_upsert_endpoint(request_body: dict):
        return JSONResponse({"status": "ok"})

    @app.get("/api/v1/memory/search")
    async def search_endpoint():
        return JSONResponse({"results": []})

    return app


class TestSecretScanMiddlewareIntegration:
    def _post(self, app, path: str, body: dict):
        """Synchronous helper using AsyncClient."""
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                return await c.post(path, json=body)

        return asyncio.run(_run())

    def _patch(self, app, path: str, body: dict):
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                return await c.patch(path, json=body)

        return asyncio.run(_run())

    def _get(self, app, path: str):
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                return await c.get(path)

        return asyncio.run(_run())

    def test_clean_write_passes_through(self, test_app):
        r = self._post(test_app, "/api/v1/memory/write", {"content": "normal content"})
        assert r.status_code == 200

    def test_secret_in_write_blocked_with_400(self, test_app):
        r = self._post(
            test_app,
            "/api/v1/memory/write",
            {"content": "sk-abcdefghijklmnopqrstuvwxyz1234"},
        )
        assert r.status_code == 400

    def test_blocked_response_has_error_envelope(self, test_app):
        r = self._post(
            test_app,
            "/api/v1/memory/write",
            {"content": "sk-abcdefghijklmnopqrstuvwxyz1234"},
        )
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == "secret_detected"
        assert body["error"]["retryable"] is False

    def test_secret_in_write_many_blocked(self, test_app):
        r = self._post(
            test_app,
            "/api/v1/memory/write-many",
            {"records": [{"content": "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"}]},
        )
        assert r.status_code == 400

    def test_secret_in_patch_blocked(self, test_app):
        r = self._patch(
            test_app,
            "/api/v1/memory/mem-123",
            {"content": "-----BEGIN RSA PRIVATE KEY-----\ndata"},
        )
        assert r.status_code == 400

    def test_secret_in_bulk_upsert_blocked(self, test_app):
        r = self._post(
            test_app,
            "/api/v1/memory/bulk-upsert",
            [{"content": "normal"}, {"content": "api_key=supersecretvalue123"}],
        )
        assert r.status_code == 400

    def test_get_endpoint_not_scanned(self, test_app):
        """GET requests must never be blocked by the scanner."""
        r = self._get(test_app, "/api/v1/memory/search")
        assert r.status_code == 200

    def test_non_json_body_passes_through(self, test_app):
        """Non-parseable bodies must not crash the middleware."""
        import asyncio
        from httpx import ASGITransport, AsyncClient

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as c:
                return await c.post(
                    "/api/v1/memory/write",
                    content=b"not json at all",
                    headers={"content-type": "application/json"},
                )

        r = asyncio.run(_run())
        # Middleware must not return 400 for parse errors — let FastAPI handle it
        assert (
            r.status_code != 400
            or r.json().get("error", {}).get("code") != "secret_detected"
        )
