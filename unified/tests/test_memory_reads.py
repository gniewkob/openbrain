"""Targeted tests for uncovered branches in src/memory_reads.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    return s


def _mock_memory_out(
    id="m1",
    title="Test",
    entity_type="Note",
    content="hello",
    tags=None,
    domain="build",
):
    m = MagicMock()
    m.id = id
    m.title = title
    m.entity_type = entity_type
    m.content = content
    m.tags = tags or []
    m.domain = domain
    return m


def _mock_record(**kwargs):
    """Build a MemoryRecord-like MagicMock."""
    r = MagicMock()
    for k, v in kwargs.items():
        setattr(r, k, v)
    r.tags = kwargs.get("tags", [])
    r.entity_type = kwargs.get("entity_type", "Note")
    r.content = kwargs.get("content", "test content")
    r.title = kwargs.get("title", "Test")
    r.id = kwargs.get("id", "m1")
    return r


# ---------------------------------------------------------------------------
# get_memory_as_record — happy path (record found)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_as_record_returns_both_when_found():
    from src.memory_reads import get_memory_as_record

    session = _make_session()
    mock_mem = MagicMock()

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_mem
    session.execute = AsyncMock(return_value=res_mock)

    with (
        patch("src.memory_reads._to_record", return_value=MagicMock()) as mock_to_record,
        patch("src.memory_reads._to_out", return_value=MagicMock()) as mock_to_out,
    ):
        record, out = await get_memory_as_record(session, "m1")

    mock_to_record.assert_called_once_with(mock_mem)
    mock_to_out.assert_called_once_with(mock_mem)


# ---------------------------------------------------------------------------
# get_memory_with_repo — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_with_repo_returns_none_when_missing():
    from src.memory_reads import get_memory_with_repo

    session = _make_session()
    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=None)

    with patch("src.memory_reads.get_repository", return_value=mock_repo):
        result = await get_memory_with_repo(session, "missing-id")

    assert result is None


@pytest.mark.asyncio
async def test_get_memory_with_repo_returns_out_when_found():
    from src.memory_reads import get_memory_with_repo

    session = _make_session()
    mock_mem = MagicMock()
    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=mock_mem)

    with (
        patch("src.memory_reads.get_repository", return_value=mock_repo),
        patch("src.memory_reads._to_out", return_value=MagicMock()) as mock_to_out,
    ):
        result = await get_memory_with_repo(session, "m1")

    mock_to_out.assert_called_once_with(mock_mem)


# ---------------------------------------------------------------------------
# sync_check — ValueError when no identifier provided
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_check_raises_value_error_when_no_identifier():
    from src.memory_reads import sync_check

    session = _make_session()
    with pytest.raises(ValueError, match="Exactly one"):
        await sync_check(session)


# ---------------------------------------------------------------------------
# get_grounding_pack — owner/tenant_id filters + response construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_grounding_pack_with_owner_and_tenant():
    from src.memory_reads import get_grounding_pack
    from src.schemas import MemoryGetContextRequest

    session = _make_session()
    record = _mock_record(content="short content", entity_type="Note", tags=["ai"])
    hits = [(record, 0.9)]

    req = MemoryGetContextRequest(query="test query", max_items=5)

    with patch("src.memory_reads.find_memories_v1", AsyncMock(return_value=hits)):
        result = await get_grounding_pack(session, req, owner="alice", tenant_id="t1")

    assert result.query == "test query"
    assert len(result.records) == 1
    assert "ai" in result.themes


@pytest.mark.asyncio
async def test_get_grounding_pack_excerpts_long_content():
    from src.memory_reads import get_grounding_pack
    from src.schemas import MemoryGetContextRequest

    session = _make_session()
    long_content = "x" * 400
    record = _mock_record(content=long_content, entity_type="Note", tags=[])
    hits = [(record, 0.8)]

    req = MemoryGetContextRequest(query="q")
    with patch("src.memory_reads.find_memories_v1", AsyncMock(return_value=hits)):
        result = await get_grounding_pack(session, req)

    excerpt = result.records[0]["excerpt"]
    assert excerpt.endswith("...")
    assert len(excerpt) == 303  # 300 chars + "..."


@pytest.mark.asyncio
async def test_get_grounding_pack_collects_risks():
    from src.memory_reads import get_grounding_pack
    from src.schemas import MemoryGetContextRequest

    session = _make_session()
    risk_record = _mock_record(entity_type="Risk", content="security vulnerability", tags=[])
    hits = [(risk_record, 0.95)]

    req = MemoryGetContextRequest(query="risks")
    with patch("src.memory_reads.find_memories_v1", AsyncMock(return_value=hits)):
        result = await get_grounding_pack(session, req)

    assert "security vulnerability" in result.risks


@pytest.mark.asyncio
async def test_get_grounding_pack_no_hits_returns_empty():
    from src.memory_reads import get_grounding_pack
    from src.schemas import MemoryGetContextRequest

    session = _make_session()
    req = MemoryGetContextRequest(query="nothing")
    with patch("src.memory_reads.find_memories_v1", AsyncMock(return_value=[])):
        result = await get_grounding_pack(session, req)

    assert result.records == []
    assert result.themes == []
    assert result.risks == []


# ---------------------------------------------------------------------------
# _apply_filters_to_stmt — filter branches via list_memories mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_memories_with_domain_list_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    # domain as list — exercises the isinstance branch
    result = await list_memories(session, {"domain": ["build", "personal"]})
    assert result == []


@pytest.mark.asyncio
async def test_list_memories_with_entity_type_list_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    result = await list_memories(session, {"entity_type": ["Note", "Decision"]})
    assert result == []


@pytest.mark.asyncio
async def test_list_memories_with_sensitivity_and_tags_any_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    result = await list_memories(
        session, {"sensitivity": "internal", "tags_any": ["ai", "code"]}
    )
    assert result == []


@pytest.mark.asyncio
async def test_list_memories_with_owner_list_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    result = await list_memories(session, {"owner": ["alice", "bob"]})
    assert result == []


@pytest.mark.asyncio
async def test_list_memories_with_tenant_id_list_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    result = await list_memories(session, {"tenant_id": ["t1", "t2"]})
    assert result == []


@pytest.mark.asyncio
async def test_list_memories_with_tenant_id_scalar_filter():
    from src.memory_reads import list_memories

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute = AsyncMock(return_value=mock_result)

    result = await list_memories(session, {"tenant_id": "tenant-1"})
    assert result == []
