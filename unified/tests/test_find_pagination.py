# tests/test_find_pagination.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestFindPagination:
    def test_find_request_default_offset_is_zero(self):
        from src.schemas import MemoryFindRequest
        req = MemoryFindRequest(query="test")
        assert req.offset == 0

    def test_find_request_accepts_positive_offset(self):
        from src.schemas import MemoryFindRequest
        req = MemoryFindRequest(query="test", offset=20)
        assert req.offset == 20

    def test_find_request_rejects_negative_offset(self):
        from pydantic import ValidationError
        from src.schemas import MemoryFindRequest
        with pytest.raises(ValidationError):
            MemoryFindRequest(query="test", offset=-1)

    def test_find_request_offset_is_in_schema(self):
        from src.schemas import MemoryFindRequest
        fields = MemoryFindRequest.model_fields
        assert "offset" in fields


@pytest.mark.asyncio
async def test_find_memories_v1_passes_offset_to_sql():
    """find_memories_v1 must apply offset to the SQL statement."""
    from src.memory_reads import find_memories_v1
    from src.schemas import MemoryFindRequest

    req = MemoryFindRequest(query=None, limit=5, offset=10)
    session = AsyncMock()

    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    captured_stmts = []
    original_execute = session.execute

    async def capturing_execute(stmt, *args, **kwargs):
        try:
            from sqlalchemy.dialects import postgresql
            compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            captured_stmts.append(str(compiled))
        except Exception:
            captured_stmts.append(repr(stmt))
        return await original_execute(stmt, *args, **kwargs)

    session.execute = capturing_execute

    await find_memories_v1(session, req)

    assert captured_stmts, "session.execute was never called"
    sql = captured_stmts[0].upper()
    assert "OFFSET" in sql, f"Expected OFFSET in SQL but got:\n{captured_stmts[0]}"


import re as _re


@pytest.mark.asyncio
async def test_find_memories_custom_fields_filter_applied():
    """custom_fields filter must produce SQL filtering on metadata_ JSONB path."""
    from src.memory_reads import find_memories_v1
    from src.schemas import MemoryFindRequest

    req = MemoryFindRequest(
        query=None,
        limit=5,
        filters={"custom_fields": {"status": "active"}},
    )
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    captured_stmts = []
    original_execute = session.execute

    async def capturing_execute(stmt, *args, **kwargs):
        try:
            from sqlalchemy.dialects import postgresql
            compiled = stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
            captured_stmts.append(str(compiled))
        except Exception:
            captured_stmts.append(repr(stmt))
        return await original_execute(stmt, *args, **kwargs)

    session.execute = capturing_execute
    await find_memories_v1(session, req)

    assert captured_stmts, "session.execute was never called"
    sql = captured_stmts[0]
    assert "custom_fields" in sql or "metadata" in sql, (
        f"Expected custom_fields/metadata in SQL but got:\n{sql}"
    )


def test_apply_filters_custom_fields_bad_key_raises():
    """Keys with invalid chars must raise ValueError."""
    from src.memory_reads import _apply_filters_to_stmt
    from src.models import Memory
    from sqlalchemy import select

    stmt = select(Memory)
    with pytest.raises(ValueError, match="custom_fields key"):
        _apply_filters_to_stmt(
            stmt,
            {"custom_fields": {"bad key!": "val"}},
            default_status_filter=False,
        )


def test_apply_filters_custom_fields_non_dict_raises():
    """Non-dict custom_fields must raise ValueError."""
    from src.memory_reads import _apply_filters_to_stmt
    from src.models import Memory
    from sqlalchemy import select

    stmt = select(Memory)
    with pytest.raises(ValueError, match="must be a dict"):
        _apply_filters_to_stmt(
            stmt,
            {"custom_fields": "not_a_dict"},
            default_status_filter=False,
        )


def test_apply_filters_custom_fields_valid_key_accepted():
    """Valid key chars must not raise."""
    from src.memory_reads import _apply_filters_to_stmt
    from src.models import Memory
    from sqlalchemy import select

    stmt = select(Memory)
    # Should not raise
    result = _apply_filters_to_stmt(
        stmt,
        {"custom_fields": {"my_field-1": "value", "status.ok": "yes"}},
        default_status_filter=False,
    )
    assert result is not None
