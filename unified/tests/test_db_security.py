from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch


DB_MODULE = "src.db"


class DatabaseSecurityTests(unittest.TestCase):
    def _reload_db(self):
        sys.modules.pop(DB_MODULE, None)
        return importlib.import_module(DB_MODULE)

    def test_public_mode_rejects_dev_default_database_credentials(self) -> None:
        dev_url = "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"
        
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "true",
                "DATABASE_URL": dev_url,
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids dev default PostgreSQL credentials"
            ):
                self._reload_db()

    def test_public_mode_allows_non_default_database_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "true",
                "DATABASE_URL": "postgresql+asyncpg://postgres:strong-secret@db:5432/openbrain_unified",
            },
            clear=False,
        ):
            module = self._reload_db()
        self.assertFalse(module._uses_dev_database_credentials(module.DB_URL))

    def test_public_base_url_rejects_dev_default_database_credentials(self) -> None:
        dev_url = "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"

        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "false",
                "PUBLIC_BASE_URL": "https://example.ngrok-free.dev",
                "DATABASE_URL": dev_url,
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids dev default PostgreSQL credentials"
            ):
                self._reload_db()

    def test_no_runtime_flag_can_disable_public_database_validation(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLIC_MODE": "true",
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified",
                "OPENBRAIN_DISABLE_DB_CONFIG_VALIDATION": "true",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids dev default PostgreSQL credentials"
            ):
                self._reload_db()


if __name__ == "__main__":
    unittest.main()
