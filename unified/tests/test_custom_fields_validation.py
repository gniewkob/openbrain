"""Tests for custom_fields size and content validation across schema classes."""

import json

import pytest
from pydantic import ValidationError

from src.schemas import MemoryUpdate, MemoryUpsertItem, MemoryWriteRecord

_WRITE_BASE = dict(domain="build", entity_type="Note", content="x", owner="u")


class TestValidCases:
    """custom_fields accepted by the validator."""

    def test_empty_dict(self):
        r = MemoryWriteRecord(**_WRITE_BASE, custom_fields={})
        assert r.custom_fields == {}

    def test_all_scalar_types(self):
        cf = {"s": "text", "i": 1, "f": 3.14, "b": True, "n": None}
        r = MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)
        assert r.custom_fields["s"] == "text"
        assert r.custom_fields["n"] is None

    def test_exactly_20_keys(self):
        cf = {f"k{i:02d}": i for i in range(20)}
        r = MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)
        assert len(r.custom_fields) == 20

    def test_key_patterns_allowed(self):
        cf = {"a_b": 1, "a-b": 2, "a.b": 3, "A1": 4}
        r = MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)
        assert len(r.custom_fields) == 4

    def test_string_value_256_chars(self):
        r = MemoryWriteRecord(**_WRITE_BASE, custom_fields={"k": "x" * 256})
        assert len(r.custom_fields["k"]) == 256

    def test_under_5kb(self):
        cf = {f"k{i:02d}": "a" * 50 for i in range(20)}
        size = len(json.dumps(cf, separators=(",", ":")))
        assert size < 5120
        MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)

    def test_memory_update_none_allowed(self):
        u = MemoryUpdate(custom_fields=None)
        assert u.custom_fields is None

    def test_upsert_item_valid(self):
        r = MemoryUpsertItem(content="x", custom_fields={"key": "val"})
        assert r.custom_fields["key"] == "val"


class TestInvalidCases:
    """custom_fields rejected by the validator."""

    def test_too_many_keys(self):
        cf = {f"k{i:02d}": i for i in range(21)}
        with pytest.raises(ValidationError, match="20"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)

    def test_key_too_long(self):
        with pytest.raises(ValidationError, match="64"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields={"k" * 65: "v"})

    def test_key_invalid_chars(self):
        for bad_key in ["k@v", "k v", "k/v", "k:v", "k$v"]:
            with pytest.raises(ValidationError, match=r"\^"):
                MemoryWriteRecord(**_WRITE_BASE, custom_fields={bad_key: "v"})

    def test_value_string_too_long(self):
        with pytest.raises(ValidationError, match="256"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields={"k": "x" * 257})

    def test_value_type_list(self):
        with pytest.raises(ValidationError, match="list"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields={"k": [1, 2]})

    def test_value_type_dict(self):
        with pytest.raises(ValidationError, match="dict"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields={"k": {"nested": True}})

    def test_exceeds_5kb(self):
        # 20 keys × 256 char values ≈ 5.4 KB
        cf = {f"k{i:02d}": "z" * 256 for i in range(20)}
        size = len(json.dumps(cf, separators=(",", ":")))
        assert size > 5120
        with pytest.raises(ValidationError, match="5120"):
            MemoryWriteRecord(**_WRITE_BASE, custom_fields=cf)

    def test_memory_update_invalid_when_provided(self):
        with pytest.raises(ValidationError, match="20"):
            MemoryUpdate(custom_fields={f"k{i:02d}": i for i in range(21)})

    def test_upsert_item_invalid(self):
        with pytest.raises(ValidationError, match="20"):
            MemoryUpsertItem(
                content="x",
                custom_fields={f"k{i:02d}": i for i in range(21)},
            )
