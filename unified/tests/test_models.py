import unittest
from datetime import datetime, timezone
import uuid
import hashlib

from src.models import compute_hash, _now, _uuid, DomainEnum

class ModelsTests(unittest.TestCase):
    def test_compute_hash_happy_path(self):
        """Test compute_hash generates expected SHA-256 for basic strings."""
        content = "hello world"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_compute_hash_empty_string(self):
        """Test compute_hash generates correct hash for an empty string."""
        content = ""
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_compute_hash_unicode(self):
        """Test compute_hash works with unicode characters."""
        content = "hello 🌍"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash(content), expected)

    def test_now_returns_utc(self):
        """Test _now returns a timezone-aware UTC datetime."""
        dt = _now()
        self.assertIsInstance(dt, datetime)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_uuid_returns_valid_string(self):
        """Test _uuid returns a valid string representation of a UUID4."""
        val = _uuid()
        self.assertIsInstance(val, str)
        # Should not raise ValueError
        parsed = uuid.UUID(val, version=4)
        self.assertEqual(str(parsed), val)

    def test_domain_enum_values(self):
        """Test DomainEnum has correct values defined."""
        self.assertEqual(DomainEnum.corporate.value, "corporate")
        self.assertEqual(DomainEnum.build.value, "build")
        self.assertEqual(DomainEnum.personal.value, "personal")

if __name__ == '__main__':
    unittest.main()
