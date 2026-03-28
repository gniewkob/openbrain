from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from tests.test_metrics import _import_main_with_fake_auth_deps
from src.schemas import PolicyRegistry


main = _import_main_with_fake_auth_deps()


AUTH_MODULE = "src.auth"


class PolicyRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_policy_registry_requires_admin(self) -> None:
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                await main.read_policy_registry(_user={"sub": "user-1"})
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_update_policy_registry_round_trips_via_main(self) -> None:
        registry = PolicyRegistry(
            tenants={"tenant-a": {"write_domains": ["build"]}},
            subjects={"admin@example.com": {"admin_domains": ["corporate", "build", "personal"]}},
        )
        with patch.object(main, "PUBLIC_MODE", True), patch.object(main, "is_privileged_user", return_value=True):
            saved = await main.update_policy_registry(registry=registry, _user={"sub": "admin"})
        self.assertEqual(saved.tenants["tenant-a"].write_domains, ["build"])
        self.assertEqual(saved.subjects["admin@example.com"].admin_domains, ["corporate", "build", "personal"])

    def test_auth_loads_registry_from_file(self) -> None:
        fake_jose = types.ModuleType("jose")
        fake_jose.jwt = types.SimpleNamespace(decode=lambda *args, **kwargs: {})
        fake_jwt = types.ModuleType("jwt")

        class FakePyJWKClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def get_signing_key_from_jwt(self, token):
                return types.SimpleNamespace(key="fake-key")

        fake_jwt.PyJWKClient = FakePyJWKClient

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "policy-registry.json"
            registry_path.write_text(json.dumps({"tenants": {"tenant-a": {"read_domains": ["build"]}}}), encoding="utf-8")

            existing_jose = sys.modules.get("jose")
            existing_jwt = sys.modules.get("jwt")
            sys.modules.pop(AUTH_MODULE, None)
            sys.modules["jose"] = fake_jose
            sys.modules["jwt"] = fake_jwt
            try:
                with patch.dict(
                    os.environ,
                    {
                        "PUBLIC_MODE": "false",
                        "OPENBRAIN_POLICY_REGISTRY_JSON": "",
                        "OPENBRAIN_POLICY_REGISTRY_PATH": str(registry_path),
                    },
                    clear=False,
                ):
                    auth = importlib.import_module(AUTH_MODULE)
            finally:
                if existing_jose is not None:
                    sys.modules["jose"] = existing_jose
                else:
                    sys.modules.pop("jose", None)
                if existing_jwt is not None:
                    sys.modules["jwt"] = existing_jwt
                else:
                    sys.modules.pop("jwt", None)

        self.assertEqual(auth.get_registry_domain_scope("", "tenant-a", "read"), {"build"})


if __name__ == "__main__":
    unittest.main()
