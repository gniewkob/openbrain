from __future__ import annotations

import asyncio
import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch

from starlette.requests import Request


AUTH_MODULE = "src.auth"


class AuthSecurityTests(unittest.TestCase):
    def _reload_auth(self):
        fake_jwt = types.ModuleType("jwt")
        fake_jwt.decode = lambda *args, **kwargs: {}

        class FakePyJWKClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def get_signing_key_from_jwt(self, token):
                return types.SimpleNamespace(key="fake-key")

        fake_jwt.PyJWKClient = FakePyJWKClient

        existing_jwt = sys.modules.get("jwt")
        sys.modules.pop(AUTH_MODULE, None)
        sys.modules["jwt"] = fake_jwt
        try:
            return importlib.import_module(AUTH_MODULE)
        finally:
            if existing_jwt is not None:
                sys.modules["jwt"] = existing_jwt
            else:
                sys.modules.pop("jwt", None)

    def test_public_mode_requires_oidc_issuer(self) -> None:
        from src.auth import validate_security_configuration

        with (
            patch("src.auth.PUBLIC_EXPOSURE", True),
            patch("src.auth.OIDC_ISSUER_URL", ""),
            patch("src.auth.INTERNAL_API_KEY", ""),
            patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "openbrain-local-dev"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "requires either OIDC_ISSUER_URL"
            ):
                validate_security_configuration()

    def test_public_mode_rejects_dev_default_internal_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "true",
                "OIDC_ISSUER_URL": "https://issuer.example.com",
                "INTERNAL_API_KEY": "openbrain-local-dev",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids the dev default INTERNAL_API_KEY"
            ):
                self._reload_auth()

    def test_public_base_url_requires_oidc_issuer(self) -> None:
        from src.auth import validate_security_configuration

        with (
            patch("src.auth.PUBLIC_EXPOSURE", True),
            patch("src.auth.OIDC_ISSUER_URL", ""),
            patch("src.auth.INTERNAL_API_KEY", ""),
            patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "openbrain-local-dev"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "requires either OIDC_ISSUER_URL"
            ):
                validate_security_configuration()

    def test_policy_registry_json_must_be_valid(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "false",
                "OPENBRAIN_POLICY_REGISTRY_JSON": "{not-json",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
                self._reload_auth()

    def test_local_mode_logs_warning_once_when_auth_is_disabled(self) -> None:
        with patch.dict(os.environ, {"PUBLIC_MODE": "false", "PUBLIC_BASE_URL": ""}):
            from src import config

            config.get_config.cache_clear()
            auth = self._reload_auth()
            request = Request({"type": "http", "headers": []})

            with patch.object(auth.logger, "warning") as warning:
                result_one = asyncio.run(
                    auth.require_auth(request=request, credentials=None)
                )
                result_two = asyncio.run(
                    auth.require_auth(request=request, credentials=None)
                )

            self.assertEqual(result_one, {"sub": "local-dev"})
            self.assertEqual(result_two, {"sub": "local-dev"})
            warning.assert_called_once()

    def test_oidc_verifier_creates_refresh_lock_lazily(self) -> None:
        auth = self._reload_auth()
        verifier = auth.OIDCVerifier("https://issuer.example.com")
        self.assertIsNone(verifier._refresh_lock)

    def test_no_oidc_in_public_mode_returns_401_not_503(self) -> None:
        """When OIDC is unavailable in public mode, require_auth must return 401."""
        from fastapi import HTTPException

        auth = self._reload_auth()
        request = Request({"type": "http", "headers": []})

        with (
            patch.object(auth, "PUBLIC_EXPOSURE", True),
            patch.object(auth, "INTERNAL_API_KEY", ""),
            patch.object(auth, "_oidc", None),
        ):
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"x-internal-key", b"")],
                    "query_string": b"",
                    "method": "GET",
                    "path": "/",
                }
            )
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(auth.require_auth(request=request, credentials=None))
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertNotEqual(ctx.exception.status_code, 503)


class RateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        from src import auth

        # Reset rate limit store between tests
        auth._rate_limit_store.clear()

    def test_rate_limit_function_exists(self) -> None:
        from src.auth import check_internal_key_rate_limit

        self.assertTrue(callable(check_internal_key_rate_limit))

    def test_requests_within_limit_pass(self) -> None:
        with patch.dict(os.environ, {"AUTH_RATE_LIMIT_RPM": "5"}):
            from src.auth import check_internal_key_rate_limit, _rate_limit_store

            _rate_limit_store.clear()
            for _ in range(5):
                check_internal_key_rate_limit("192.0.2.1")  # must not raise

    def test_exceeding_limit_raises_429(self) -> None:
        from fastapi import HTTPException

        with patch.dict(os.environ, {"AUTH_RATE_LIMIT_RPM": "3"}):
            from src.auth import check_internal_key_rate_limit, _rate_limit_store

            _rate_limit_store.clear()
            for _ in range(3):
                check_internal_key_rate_limit("192.0.2.2")
            with self.assertRaises(HTTPException) as ctx:
                check_internal_key_rate_limit("192.0.2.2")
            self.assertEqual(ctx.exception.status_code, 429)

    def test_different_ips_have_independent_limits(self) -> None:
        with patch.dict(os.environ, {"AUTH_RATE_LIMIT_RPM": "2"}):
            from src.auth import check_internal_key_rate_limit, _rate_limit_store

            _rate_limit_store.clear()
            check_internal_key_rate_limit("10.0.0.1")
            check_internal_key_rate_limit("10.0.0.1")
            # 10.0.0.1 is now at limit, 10.0.0.2 should still work
            check_internal_key_rate_limit("10.0.0.2")  # must not raise

    def test_stale_ips_evicted_when_store_exceeds_cap(self) -> None:
        """When _rate_limit_store exceeds _MAX_RATE_LIMIT_IPS, stale entries are removed."""
        import collections
        import time
        from unittest.mock import patch as mpatch

        from src.auth import (
            _MAX_RATE_LIMIT_IPS,
            _rate_limit_store,
            check_internal_key_rate_limit,
        )

        _rate_limit_store.clear()

        # Fill store with _MAX_RATE_LIMIT_IPS stale entries (old timestamps → empty windows)
        stale_time = time.time() - 120  # 2 minutes ago — outside 60s window
        for i in range(_MAX_RATE_LIMIT_IPS):
            dq = collections.deque()
            dq.append(stale_time)
            _rate_limit_store[f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"] = dq

        # Force in-memory path regardless of REDIS_URL env in CI.
        with mpatch("src.auth._get_redis_client", return_value=None):
            check_internal_key_rate_limit("192.0.2.100")

        # Store should be much smaller now — all stale IPs evicted
        self.assertLess(len(_rate_limit_store), _MAX_RATE_LIMIT_IPS)


if __name__ == "__main__":
    unittest.main()
