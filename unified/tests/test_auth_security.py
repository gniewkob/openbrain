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
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "true",
                "OIDC_ISSUER_URL": "",
                "INTERNAL_API_KEY": "super-secret",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires OIDC_ISSUER_URL"):
                self._reload_auth()

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
            with self.assertRaisesRegex(RuntimeError, "forbids the dev default INTERNAL_API_KEY"):
                self._reload_auth()

    def test_public_base_url_requires_oidc_issuer(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "false",
                "PUBLIC_BASE_URL": "https://example.ngrok-free.dev",
                "OIDC_ISSUER_URL": "",
                "INTERNAL_API_KEY": "super-secret",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires OIDC_ISSUER_URL"):
                self._reload_auth()

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
        auth = self._reload_auth()
        request = Request({"type": "http", "headers": []})

        with patch.object(auth.logger, "warning") as warning:
            result_one = asyncio.run(auth.require_auth(request=request, credentials=None))
            result_two = asyncio.run(auth.require_auth(request=request, credentials=None))

        self.assertEqual(result_one, {"sub": "local-dev"})
        self.assertEqual(result_two, {"sub": "local-dev"})
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
