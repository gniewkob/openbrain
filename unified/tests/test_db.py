from __future__ import annotations

import os
import sys
import importlib
import unittest
from unittest.mock import patch

class TestDatabaseConfiguration(unittest.TestCase):
    def _reload_module(self):
        # We need to reload to simulate module-level evaluation of DB_URL and validate_database_configuration
        sys.modules.pop("src.db", None)
        return importlib.import_module("src.db")

    def test_uses_dev_credentials_with_standard_dev_credentials(self) -> None:
        db = self._reload_module()
        self.assertTrue(
            db._uses_dev_database_credentials(
                "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"
            )
        )
        self.assertTrue(
            db._uses_dev_database_credentials(
                "postgresql://postgres:postgres@db:5432/openbrain_unified"
            )
        )

    def test_uses_dev_credentials_with_passwordless_dev_credentials(self) -> None:
        db = self._reload_module()
        self.assertTrue(
            db._uses_dev_database_credentials(
                "postgresql+asyncpg://postgres@db:5432/openbrain_unified"
            )
        )

    def test_uses_dev_credentials_with_non_dev_user(self) -> None:
        db = self._reload_module()
        self.assertFalse(
            db._uses_dev_database_credentials(
                "postgresql+asyncpg://otheruser:postgres@db:5432/openbrain_unified"
            )
        )

    def test_uses_dev_credentials_with_non_dev_password(self) -> None:
        db = self._reload_module()
        self.assertFalse(
            db._uses_dev_database_credentials(
                "postgresql+asyncpg://postgres:securepassword@db:5432/openbrain_unified"
            )
        )

    def test_uses_dev_credentials_with_invalid_url(self) -> None:
        db = self._reload_module()
        self.assertFalse(db._uses_dev_database_credentials("invalid_url_format"))
        self.assertFalse(db._uses_dev_database_credentials(""))

    @patch.dict(os.environ, {"PUBLIC_MODE": "true", "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"}, clear=True)
    def test_validate_database_config_public_mode_dev_creds(self) -> None:
        with self.assertRaises(RuntimeError):
            self._reload_module()

    @patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://example.com", "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"}, clear=True)
    def test_validate_database_config_public_base_url_dev_creds(self) -> None:
        with self.assertRaises(RuntimeError):
            self._reload_module()

    @patch.dict(
        os.environ,
        {"PUBLIC_MODE": "true", "PUBLIC_BASE_URL": "https://example.com", "DATABASE_URL": "postgresql+asyncpg://postgres:securepassword@db:5432/openbrain_unified"},
        clear=True,
    )
    def test_validate_database_config_public_mode_non_dev_creds(self) -> None:
        # DB_URL is explicitly mocked with a secure password, so _uses_dev_database_credentials will return False
        # Should not raise since it's not dev credentials
        self._reload_module()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"}, clear=True)
    def test_validate_database_config_no_public_flags(self) -> None:
        # Should not raise even with dev creds since it's not public
        self._reload_module()

if __name__ == "__main__":
    unittest.main()
