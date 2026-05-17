import contextlib
import unittest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter

from src.app_factory import create_app, SecurityHeadersMiddleware
from src.middleware import SecretScanMiddleware


@contextlib.asynccontextmanager
async def noop_lifespan(app: FastAPI):
    yield


class TestAppFactory(unittest.TestCase):
    def setUp(self):
        # Create a mock AppConfig instance
        self.mock_app_config = MagicMock()
        self.mock_app_config.auth.public_mode = False
        self.mock_app_config.auth.public_base_url = ""
        self.mock_app_config.rate_limit_per_minute = 100
        self.mock_app_config.redis.url = "memory://"
        self.mock_app_config.cors.get_origins_list.return_value = []

    @patch("src.app_factory.get_config")
    def test_create_app_local_mode(self, mock_get_config):
        mock_get_config.return_value = self.mock_app_config

        # In local mode: docs are enabled, cors allows regex for localhost
        app = create_app(lifespan=noop_lifespan)

        self.assertIsInstance(app, FastAPI)
        self.assertEqual(app.title, "OpenBrain Unified Memory Service")
        self.assertEqual(app.docs_url, "/docs")
        self.assertEqual(app.openapi_url, "/openapi.json")

        # Check middlewares
        middleware_classes = [m.cls for m in app.user_middleware]

        self.assertIn(SecurityHeadersMiddleware, middleware_classes)
        self.assertIn(SecretScanMiddleware, middleware_classes)
        self.assertIn(CORSMiddleware, middleware_classes)

        # Check rate limiter
        self.assertTrue(hasattr(app.state, "limiter"))
        self.assertIsInstance(app.state.limiter, Limiter)

    @patch("src.app_factory.get_config")
    def test_create_app_public_mode(self, mock_get_config):
        self.mock_app_config.auth.public_mode = True
        self.mock_app_config.cors.get_origins_list.return_value = [
            "https://example.com"
        ]
        mock_get_config.return_value = self.mock_app_config

        app = create_app(public_base_url="https://example.com", lifespan=noop_lifespan)

        self.assertIsInstance(app, FastAPI)
        # Docs should be disabled in public mode
        self.assertIsNone(app.docs_url)
        self.assertIsNone(app.openapi_url)

        # Check servers configuration
        self.assertEqual(app.servers, [{"url": "https://example.com"}])

    @patch("src.app_factory.get_config")
    def test_security_headers_middleware_local(self, mock_get_config):
        mock_get_config.return_value = self.mock_app_config
        app = create_app(lifespan=noop_lifespan)
        client = TestClient(app)

        @app.get("/test-headers")
        async def test_endpoint():
            return {"message": "ok"}

        response = client.get("/test-headers")
        self.assertEqual(response.status_code, 200)

        # Security headers should be present
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-XSS-Protection"], "1; mode=block")
        self.assertEqual(
            response.headers["Referrer-Policy"], "strict-origin-when-cross-origin"
        )
        self.assertEqual(
            response.headers["Content-Security-Policy"],
            "default-src 'none'; frame-ancestors 'none'",
        )

        # In local mode, HSTS should NOT be set
        self.assertNotIn("Strict-Transport-Security", response.headers)

    @patch("src.app_factory.get_config")
    def test_security_headers_middleware_public(self, mock_get_config):
        self.mock_app_config.auth.public_mode = True
        self.mock_app_config.auth.public_base_url = "https://example.com"
        self.mock_app_config.cors.get_origins_list.return_value = [
            "https://example.com"
        ]
        mock_get_config.return_value = self.mock_app_config

        app = create_app(public_base_url="https://example.com", lifespan=noop_lifespan)
        client = TestClient(app)

        @app.get("/test-headers")
        async def test_endpoint():
            return {"message": "ok"}

        response = client.get("/test-headers")
        self.assertEqual(response.status_code, 200)

        # Security headers should be present
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

        # In public mode, HSTS SHOULD be set
        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains",
        )


if __name__ == "__main__":
    unittest.main()
