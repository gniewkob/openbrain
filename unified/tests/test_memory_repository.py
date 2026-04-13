"""Tests for InMemoryMemoryRepository — repository pattern CRUD + search."""

import pytest
from unittest.mock import MagicMock

from src.repositories.memory_repository import InMemoryMemoryRepository
from src.schemas import MemoryCreate, MemoryUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_data(**kwargs) -> MemoryCreate:
    defaults = dict(content="hello world", domain="build", entity_type="Note")
    defaults.update(kwargs)
    return MemoryCreate(**defaults)


def _seeded_memory(memory_id: str = "mem_1", match_key: str | None = None, **kwargs):
    """Return a minimal MagicMock that acts as a Memory ORM record."""
    mem = MagicMock()
    mem.id = memory_id
    mem.match_key = match_key
    mem.domain = kwargs.get("domain", "build")
    mem.entity_type = kwargs.get("entity_type", "Note")
    mem.status = kwargs.get("status", "active")
    mem.embedding = kwargs.get("embedding", None)
    return mem


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing():
    repo = InMemoryMemoryRepository()
    assert await repo.get_by_id("nonexistent") is None


@pytest.mark.asyncio
async def test_get_by_id_returns_seeded_record():
    repo = InMemoryMemoryRepository()
    mem = _seeded_memory("mem_1")
    repo.seed([mem])
    assert await repo.get_by_id("mem_1") is mem


# ---------------------------------------------------------------------------
# get_by_match_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_match_key_returns_none_when_missing():
    repo = InMemoryMemoryRepository()
    assert await repo.get_by_match_key("no-such-key") is None


@pytest.mark.asyncio
async def test_get_by_match_key_returns_seeded_record():
    repo = InMemoryMemoryRepository()
    mem = _seeded_memory("mem_1", match_key="key-a")
    repo.seed([mem])
    assert await repo.get_by_match_key("key-a") is mem


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_empty():
    repo = InMemoryMemoryRepository()
    assert await repo.list_all() == []


@pytest.mark.asyncio
async def test_list_all_returns_all():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1"), _seeded_memory("m2")])
    result = await repo.list_all()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_all_filter_by_domain():
    repo = InMemoryMemoryRepository()
    repo.seed([
        _seeded_memory("m1", domain="build"),
        _seeded_memory("m2", domain="corporate"),
    ])
    result = await repo.list_all(domain="build")
    assert len(result) == 1
    assert result[0].id == "m1"


@pytest.mark.asyncio
async def test_list_all_filter_by_entity_type():
    repo = InMemoryMemoryRepository()
    repo.seed([
        _seeded_memory("m1", entity_type="Note"),
        _seeded_memory("m2", entity_type="Fact"),
    ])
    result = await repo.list_all(entity_type="Note")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_all_filter_by_status():
    repo = InMemoryMemoryRepository()
    repo.seed([
        _seeded_memory("m1", status="active"),
        _seeded_memory("m2", status="deprecated"),
    ])
    result = await repo.list_all(status="active")
    assert len(result) == 1
    assert result[0].id == "m1"


@pytest.mark.asyncio
async def test_list_all_skip_and_limit():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory(f"m{i}") for i in range(5)])
    result = await repo.list_all(skip=2, limit=2)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_empty():
    repo = InMemoryMemoryRepository()
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_count_all():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1"), _seeded_memory("m2")])
    assert await repo.count() == 2


@pytest.mark.asyncio
async def test_count_filtered_by_domain():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1", domain="build"), _seeded_memory("m2", domain="personal")])
    assert await repo.count(domain="build") == 1


@pytest.mark.asyncio
async def test_count_filtered_by_entity_type():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1", entity_type="Note"), _seeded_memory("m2", entity_type="Fact")])
    assert await repo.count(entity_type="Fact") == 1


@pytest.mark.asyncio
async def test_count_filtered_by_status():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1", status="active"), _seeded_memory("m2", status="draft")])
    assert await repo.count(status="draft") == 1


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_memory_with_id():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data())
    assert mem.id.startswith("mem_")


@pytest.mark.asyncio
async def test_create_auto_increments_id():
    repo = InMemoryMemoryRepository()
    m1 = await repo.create(_create_data())
    m2 = await repo.create(_create_data())
    assert m1.id != m2.id


@pytest.mark.asyncio
async def test_create_stores_retrievable():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data(content="stored"))
    retrieved = await repo.get_by_id(mem.id)
    assert retrieved is not None
    assert retrieved.content == "stored"


@pytest.mark.asyncio
async def test_create_indexes_match_key():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data(match_key="idem-key"))
    by_key = await repo.get_by_match_key("idem-key")
    assert by_key is not None
    assert by_key.id == mem.id


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_returns_none_for_missing():
    repo = InMemoryMemoryRepository()
    result = await repo.update("nonexistent", MemoryUpdate())
    assert result is None


@pytest.mark.asyncio
async def test_update_modifies_content():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data(content="old"))
    updated = await repo.update(mem.id, MemoryUpdate(content="new"))
    assert updated is not None
    assert updated.content == "new"


@pytest.mark.asyncio
async def test_update_match_key_reindexes():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data(match_key="key-old"))
    await repo.update(mem.id, MemoryUpdate(obsidian_ref=None))  # No match_key change
    # Verify old key still works (update_data only modifies set fields)
    assert await repo.get_by_match_key("key-old") is not None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_false_for_missing():
    repo = InMemoryMemoryRepository()
    assert await repo.delete("nonexistent") is False


@pytest.mark.asyncio
async def test_delete_removes_record():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data())
    assert await repo.delete(mem.id) is True
    assert await repo.get_by_id(mem.id) is None


@pytest.mark.asyncio
async def test_delete_removes_match_key_index():
    repo = InMemoryMemoryRepository()
    mem = await repo.create(_create_data(match_key="del-key"))
    await repo.delete(mem.id)
    assert await repo.get_by_match_key("del-key") is None


# ---------------------------------------------------------------------------
# search_by_embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_by_embedding_empty_query_returns_empty():
    repo = InMemoryMemoryRepository()
    result = await repo.search_by_embedding([])
    assert result == []


@pytest.mark.asyncio
async def test_search_by_embedding_skips_inactive():
    repo = InMemoryMemoryRepository()
    mem = _seeded_memory("m1", status="deprecated", embedding=[1.0, 0.0])
    repo.seed([mem])
    result = await repo.search_by_embedding([1.0, 0.0])
    assert result == []


@pytest.mark.asyncio
async def test_search_by_embedding_skips_no_embedding():
    repo = InMemoryMemoryRepository()
    mem = _seeded_memory("m1", status="active", embedding=None)
    repo.seed([mem])
    result = await repo.search_by_embedding([1.0, 0.0])
    assert result == []


@pytest.mark.asyncio
async def test_search_by_embedding_returns_similar():
    repo = InMemoryMemoryRepository()
    mem = _seeded_memory("m1", status="active", embedding=[1.0, 0.0])
    repo.seed([mem])
    result = await repo.search_by_embedding([1.0, 0.0])
    assert len(result) == 1
    assert result[0][0].id == "m1"
    assert abs(result[0][1] - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_search_by_embedding_threshold_filters():
    repo = InMemoryMemoryRepository()
    mem_hi = _seeded_memory("hi", status="active", embedding=[1.0, 0.0])
    mem_lo = _seeded_memory("lo", status="active", embedding=[0.0, 1.0])
    repo.seed([mem_hi, mem_lo])
    result = await repo.search_by_embedding([1.0, 0.0], threshold=0.9)
    assert len(result) == 1
    assert result[0][0].id == "hi"


@pytest.mark.asyncio
async def test_search_by_embedding_top_k_limits():
    repo = InMemoryMemoryRepository()
    for i in range(5):
        repo.seed([_seeded_memory(f"m{i}", status="active", embedding=[float(i + 1), 0.0])])
    result = await repo.search_by_embedding([1.0, 0.0], top_k=2)
    assert len(result) <= 2


# ---------------------------------------------------------------------------
# clear / seed helpers
# ---------------------------------------------------------------------------


def test_clear_empties_storage():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1")])
    repo.clear()
    assert repo._storage == {}
    assert repo._match_key_index == {}
    assert repo._id_counter == 0


def test_seed_updates_id_counter():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("mem_42")])
    assert repo._id_counter == 42


def test_seed_ignores_non_numeric_id():
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("custom-id")])
    assert repo._id_counter == 0


def test_seed_with_non_numeric_mem_prefix_id():
    """mem_abc → ValueError in int() → except branch (lines 394-395)."""
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("mem_abc")])
    assert repo._id_counter == 0  # exception swallowed, counter unchanged


# ---------------------------------------------------------------------------
# InMemoryMemoryRepository — search_by_embedding zero-norm (line 363-364)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_skips_zero_norm_memory_embedding():
    """A stored memory with a zero-vector → query_norm==0 or mem_norm==0 continue branch."""
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1", status="active", embedding=[0.0, 0.0])])
    # Non-zero query, but stored embedding has zero norm → skipped
    result = await repo.search_by_embedding([1.0, 0.0])
    assert result == []


@pytest.mark.asyncio
async def test_search_skips_zero_norm_query_embedding():
    """A zero query vector → query_norm==0 → continue for every stored memory."""
    repo = InMemoryMemoryRepository()
    repo.seed([_seeded_memory("m1", status="active", embedding=[1.0, 0.0])])
    result = await repo.search_by_embedding([0.0, 0.0])
    assert result == []


# ---------------------------------------------------------------------------
# SQLAlchemyMemoryRepository — all methods via mocked AsyncSession
# ---------------------------------------------------------------------------


from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from src.repositories.memory_repository import SQLAlchemyMemoryRepository  # noqa: E402


def _make_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _scalar_result(value):
    """Return a mock mimicking result.scalar_one_or_none()."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar_one.return_value = value
    return r


def _scalars_result(values):
    """Return a mock mimicking result.scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


@pytest.mark.asyncio
async def test_sa_get_by_id_returns_none_when_missing():
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(None))
    repo = SQLAlchemyMemoryRepository(session)
    assert await repo.get_by_id("missing") is None


@pytest.mark.asyncio
async def test_sa_get_by_id_returns_record():
    mock_mem = MagicMock()
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(mock_mem))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.get_by_id("m1")
    assert result is mock_mem


@pytest.mark.asyncio
async def test_sa_get_by_match_key_returns_record():
    mock_mem = MagicMock()
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(mock_mem))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.get_by_match_key("key-1")
    assert result is mock_mem


@pytest.mark.asyncio
async def test_sa_list_all_with_all_filters():
    mock_mems = [MagicMock(), MagicMock()]
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalars_result(mock_mems))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.list_all(domain="build", entity_type="Note", status="active")
    assert result == mock_mems


@pytest.mark.asyncio
async def test_sa_list_all_no_filters():
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalars_result([]))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.list_all()
    assert result == []


@pytest.mark.asyncio
async def test_sa_count_with_all_filters():
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(3))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.count(domain="build", entity_type="Note", status="active")
    assert result == 3


@pytest.mark.asyncio
async def test_sa_create_adds_and_returns():
    mock_mem = MagicMock()
    session = _make_session()

    async def refresh_side_effect(obj):
        pass

    session.refresh = AsyncMock(side_effect=refresh_side_effect)
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo = SQLAlchemyMemoryRepository(session)

    with patch("src.repositories.memory_repository.Memory", return_value=mock_mem):
        result = await repo.create(_create_data())

    session.add.assert_called_once_with(mock_mem)
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_sa_update_returns_none_when_not_found():
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(None))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.update("missing", MemoryUpdate(content="x"))
    assert result is None


@pytest.mark.asyncio
async def test_sa_update_modifies_and_returns():
    mock_mem = MagicMock()
    mock_mem.content = "old"
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(mock_mem))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.update("m1", MemoryUpdate(content="new"))
    assert result is mock_mem
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_sa_delete_returns_false_when_not_found():
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(None))
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.delete("missing")
    assert result is False


@pytest.mark.asyncio
async def test_sa_delete_returns_true_when_found():
    mock_mem = MagicMock()
    session = _make_session()
    session.execute = AsyncMock(return_value=_scalar_result(mock_mem))
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    repo = SQLAlchemyMemoryRepository(session)
    result = await repo.delete("m1")
    assert result is True
    session.delete.assert_called_once_with(mock_mem)
    session.flush.assert_called_once()
