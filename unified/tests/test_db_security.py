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

    def test_public_mode_rejects_passwordless_dev_database_credentials(self) -> None:
        # The new default without hardcoded password should also be rejected in PUBLIC_MODE
        dev_url = "postgresql+asyncpg://postgres@db:5432/openbrain_unified"

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

    def test_direct_validate_public_mode_rejects_dev_defaults(self) -> None:
        from src import db

        dev_url = "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"
        with (
            patch.dict(os.environ, {"PUBLIC_MODE": "true"}, clear=False),
            patch("src.db.DB_URL", dev_url),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids dev default PostgreSQL credentials"
            ):
                db.validate_database_configuration()

    def test_direct_validate_public_base_url_rejects_dev_defaults(self) -> None:
        from src import db

        dev_url = "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"
        with (
            patch.dict(
                os.environ,
                {"PUBLIC_BASE_URL": "https://example.com", "PUBLIC_MODE": "false"},
                clear=False,
            ),
            patch("src.db.DB_URL", dev_url),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "forbids dev default PostgreSQL credentials"
            ):
                db.validate_database_configuration()

    def test_direct_validate_allows_non_public_mode(self) -> None:
        from src import db

        dev_url = "postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified"
        with (
            patch.dict(
                os.environ, {"PUBLIC_MODE": "false", "PUBLIC_BASE_URL": ""}, clear=False
            ),
            patch("src.db.DB_URL", dev_url),
        ):
            # Should not raise
            db.validate_database_configuration()

    def test_direct_validate_public_mode_allows_strong_credentials(self) -> None:
        from src import db

        strong_url = (
            "postgresql+asyncpg://postgres:strong-secret@db:5432/openbrain_unified"
        )
        with (
            patch.dict(os.environ, {"PUBLIC_MODE": "true"}, clear=False),
            patch("src.db.DB_URL", strong_url),
        ):
            # Should not raise
            db.validate_database_configuration()


if __name__ == "__main__":
    unittest.main()
