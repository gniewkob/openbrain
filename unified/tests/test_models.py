"""Tests for data models and utility functions in src/models.py."""

import unittest
import hashlib
from src.models import compute_hash


class TestModels(unittest.TestCase):
    def test_compute_hash_normal_string(self):
        """Verify compute_hash correctly hashes a normal ASCII string."""
        content = "hello world"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_compute_hash_empty_string(self):
        """Verify compute_hash correctly hashes an empty string."""
        content = ""
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_compute_hash_unicode_string(self):
        """Verify compute_hash correctly hashes strings with special/Unicode characters."""
        content = "héllo wörld 🚀"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_compute_hash_invalid_input(self):
        """Verify compute_hash raises an AttributeError when attempting to encode invalid types."""
        # compute_hash expects a string. If an int or None is passed,
        # it will fail when trying to call .encode("utf-8").
        with self.assertRaises(AttributeError):
            compute_hash(123)  # type: ignore

        with self.assertRaises(AttributeError):
            compute_hash(None)  # type: ignore

if __name__ == "__main__":
    unittest.main()
