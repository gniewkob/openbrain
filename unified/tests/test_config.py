import os
import unittest
from unittest.mock import patch

from src.config import AppConfig, get_config


class TestConfig(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test to ensure a clean state
        get_config.cache_clear()

    def tearDown(self):
        # Clear the cache after each test to avoid side effects on other tests
        get_config.cache_clear()

    def test_get_config_type(self):
        """Test that get_config returns an AppConfig instance."""
        config = get_config()
        self.assertIsInstance(config, AppConfig)

    def test_get_config_caching(self):
        """Test that get_config caches its result and returns the exact same object."""
        config1 = get_config()
        config2 = get_config()
        self.assertIs(config1, config2)

    def test_get_config_cache_clear(self):
        """Test that clearing the cache results in a new object being returned."""
        config1 = get_config()
        get_config.cache_clear()
        config2 = get_config()
        self.assertIsNot(config1, config2)

    @patch.dict(os.environ, {"PUBLIC_MODE": "true", "INTERNAL_API_KEY": "12345678901234567890123456789012"})
    def test_get_config_with_env_vars(self):
        """Test that get_config reflects environment variables when the cache is clear."""
        # Ensure cache is clear before calling to pick up the patched env var
        get_config.cache_clear()
        config1 = get_config()
        self.assertTrue(config1.auth.public_mode)

        # Patch a different env var, but don't clear the cache
        with patch.dict(os.environ, {"PUBLIC_MODE": "false", "INTERNAL_API_KEY": "12345678901234567890123456789012"}):
            # It should still return the cached object, ignoring the new env var
            config2 = get_config()
            self.assertIs(config1, config2)
            self.assertTrue(config2.auth.public_mode)

        # Clear the cache, and it should pick up the current environment (which is back to {"PUBLIC_MODE": "true"} from the decorator)
        get_config.cache_clear()
        config3 = get_config()
        # It's a new object
        self.assertIsNot(config1, config3)
        self.assertTrue(config3.auth.public_mode)

    @patch.dict(os.environ, {"PUBLIC_MODE": "false", "PUBLIC_BASE_URL": "http://example.com", "INTERNAL_API_KEY": "12345678901234567890123456789012"})
    def test_get_config_reexport_functions(self):
        """Test that backwards-compatibility re-export functions return expected values."""
        from src.config import (
            get_database_url,
            is_public_mode,
            get_public_base_url,
        )

        get_config.cache_clear()

        # Just check a couple of re-exports to ensure they use get_config()
        self.assertFalse(is_public_mode())
        self.assertEqual(get_public_base_url(), "http://example.com")

        # Test they use cache too
        config_obj = get_config()
        # modify the object to test if re-exports use it
        config_obj.auth.public_base_url = "http://modified.com"
        self.assertEqual(get_public_base_url(), "http://modified.com")

if __name__ == "__main__":
    unittest.main()
