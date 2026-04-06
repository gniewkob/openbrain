"""Tests for TenantIdStr validation rules (audit 3.2)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.schemas import MemoryWriteRecord


def _base_record(**overrides: object) -> dict:
    return {
        "content": "test",
        "domain": "build",
        "entity_type": "Test",
        **overrides,
    }


class TenantIdValidationTests(unittest.TestCase):
    def test_valid_tenant_ids_are_accepted(self) -> None:
        for tenant_id in ["acme", "acme-corp", "tenant_1", "T-2", "ABC123"]:
            with self.subTest(tenant_id=tenant_id):
                rec = MemoryWriteRecord.model_validate(
                    _base_record(tenant_id=tenant_id)
                )
                self.assertEqual(rec.tenant_id, tenant_id)

    def test_none_is_accepted(self) -> None:
        rec = MemoryWriteRecord.model_validate(_base_record(tenant_id=None))
        self.assertIsNone(rec.tenant_id)

    def test_empty_string_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryWriteRecord.model_validate(_base_record(tenant_id=""))

    def test_whitespace_only_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryWriteRecord.model_validate(_base_record(tenant_id="   "))

    def test_special_chars_rejected(self) -> None:
        for bad in ["tenant/id", "tenant id", "tenant@corp", "../etc"]:
            with self.subTest(tenant_id=bad):
                with self.assertRaises(ValidationError):
                    MemoryWriteRecord.model_validate(_base_record(tenant_id=bad))

    def test_too_long_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryWriteRecord.model_validate(_base_record(tenant_id="a" * 129))
