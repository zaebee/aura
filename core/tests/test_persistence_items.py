"""Tests for PersistenceSkill item handlers over the async ItemRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill


def _make_skill_with_session(session_mock: MagicMock) -> PersistenceSkill:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    async_sessionmaker_mock = MagicMock(return_value=session_mock)
    skill.bind(settings, (async_sessionmaker_mock, MagicMock(), None))
    return skill


def _make_async_session_mock() -> MagicMock:
    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()
    return session_mock


def _scalar_mock(value: object) -> MagicMock:
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = value
    return result_mock


@pytest.mark.asyncio
async def test_read_item_found():
    from aura_hive.hive.proteins.persistence.engine import InventoryItem

    item = InventoryItem(
        id="item-1",
        name="Room",
        base_price=200.0,
        floor_price=150.0,
        is_active=True,
        meta={},
    )
    session_mock = _make_async_session_mock()
    session_mock.query.return_value.filter_by.return_value.first.return_value = item
    session_mock.execute.return_value = _scalar_mock(item)

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("read_item", {"item_id": "item-1"})

    assert obs.success is True


@pytest.mark.asyncio
async def test_read_item_missing():
    session_mock = _make_async_session_mock()
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    session_mock.execute.return_value = _scalar_mock(None)

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("read_item", {"item_id": "nope"})

    assert obs.success is False
    assert obs.error == "item_not_found"


@pytest.mark.asyncio
async def test_read_item_requires_id():
    skill = _make_skill_with_session(_make_async_session_mock())
    obs = await skill.execute("read_item", {})

    assert obs.success is False
    assert obs.error == "item_id_required"


@pytest.mark.asyncio
async def test_get_first_item_with_many_rows():
    """get_first must not raise MultipleResultsFound when rows pile up.

    The sync code used `.first()` (implicit LIMIT 1); the async port must
    keep that property instead of `scalar_one_or_none()` on an unbounded
    select.
    """
    from aura_hive.hive.proteins.persistence.engine import InventoryItem

    item = InventoryItem(
        id="item-1",
        name="Room",
        base_price=200.0,
        floor_price=150.0,
        is_active=True,
        meta={},
    )
    session_mock = _make_async_session_mock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = item
    session_mock.execute.return_value = result_mock

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("get_first_item", {})

    assert obs.success is True


@pytest.mark.asyncio
async def test_legacy_upsert_item_creates_record():
    session_mock = _make_async_session_mock()
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    session_mock.execute.return_value = _scalar_mock(None)

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute(
        "upsert_item",
        {
            "id": "item-9",
            "name": "Room",
            "base_price": 200.0,
            "floor_price": 150.0,
        },
    )

    assert obs.success is True
    session_mock.add.assert_called_once()
    session_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_vector_search_without_query_returns_empty():
    """No query vector means no query — empty results, not a DB error."""
    session_mock = _make_async_session_mock()

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("vector_search", {"query_vector": None, "limit": 5})

    assert obs.success is True
    assert obs.metadata.to_dict()["results"] == []
    session_mock.execute.assert_not_called()


@pytest.mark.asyncio
async def test_vector_search_skips_rows_without_embedding():
    """A NULL embedding yields a NULL distance — skipped, never fatal."""
    from aura_hive.hive.proteins.persistence.engine import InventoryItem

    item = InventoryItem(
        id="item-1",
        name="Room",
        base_price=200.0,
        floor_price=150.0,
        is_active=True,
        meta={},
    )
    session_mock = _make_async_session_mock()
    result_mock = MagicMock()
    result_mock.all.return_value = [(item, None), (item, 0.05)]
    session_mock.execute.return_value = result_mock

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("vector_search", {"query_vector": [0.1] * 8, "limit": 5})

    assert obs.success is True
    results = obs.metadata.to_dict()["results"]
    assert len(results) == 1
    assert results[0]["similarity_score"] == pytest.approx(0.95)
