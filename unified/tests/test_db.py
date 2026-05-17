from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import unified.src.db as db_module
from sqlalchemy.ext.asyncio import AsyncSession


class DbModuleTests(unittest.IsolatedAsyncioTestCase):
    def _reload_db(self):
        # Prevent test interference by reloading the module with patches applied
        sys.modules.pop("unified.src.db", None)
        return importlib.import_module("unified.src.db")

    def test_uses_dev_database_credentials_exception(self):
        # Trigger the Exception block in _uses_dev_database_credentials
        # by passing an invalid argument type that lacks the replace method.
        self.assertFalse(db_module._uses_dev_database_credentials(None))

    def test_db_pool_configuration(self):
        # Test module initialization with explicit pool size settings
        with patch.dict(
            os.environ,
            {
                "DB_POOL_SIZE": "15",
                "DB_MAX_OVERFLOW": "25",
            },
        ):
            reloaded_db = self._reload_db()
            self.assertEqual(reloaded_db._DB_POOL_SIZE, 15)
            self.assertEqual(reloaded_db._DB_MAX_OVERFLOW, 25)

    async def test_get_db_session(self):
        # Test the async generator function for sessions
        session_gen = db_module.get_db_session()

        # Async generators require using __anext__
        session = await session_gen.__anext__()

        self.assertIsInstance(session, AsyncSession)

        # The generator should yield once and then complete
        with self.assertRaises(StopAsyncIteration):
            await session_gen.__anext__()


if __name__ == "__main__":
    unittest.main()
