"""Tests for PersistenceSkill deal handlers over the async DealRepository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill

_VALID_ID = "11111111-1111-1111-1111-111111111111"


def _deal_params(**overrides: object) -> dict:
    params: dict = {
        "id": _VALID_ID,
        "item_id": "item-1",
        "item_name": "Room",
        "final_price": 150.0,
        "currency": "USDC",
        "payment_memo": "memo-abc",
        "secret_content": b"secret",
        "buyer_did": "did:example:buyer",
        "expires_at": datetime.now(UTC),
    }
    params.update(overrides)
    return params


def _make_skill_with_session(session_mock: MagicMock) -> PersistenceSkill:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    sessionmaker_mock = MagicMock(return_value=session_mock)
    async_sessionmaker_mock = MagicMock(return_value=session_mock)
    skill.bind(
        settings, (sessionmaker_mock, MagicMock(), None, async_sessionmaker_mock)
    )
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
async def test_create_deal_adds_pending_row():
    session_mock = _make_async_session_mock()

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("create_deal", _deal_params())

    assert obs.success is True
    row = session_mock.add.call_args[0][0]
    assert row.payment_memo == "memo-abc"
    assert row.item_id == "item-1"
    session_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_deal_coerces_string_id_to_uuid():
    """Redis-backed dicts carry str ids; asyncpg would otherwise store a
    value lookups by UUID silently miss. The repo normalises at the boundary."""
    session_mock = _make_async_session_mock()

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("create_deal", _deal_params())

    assert obs.success is True
    row = session_mock.add.call_args[0][0]
    assert row.id == uuid.UUID(_VALID_ID)


@pytest.mark.asyncio
async def test_get_deal_by_id_missing():
    session_mock = _make_async_session_mock()
    session_mock.execute.return_value = _scalar_mock(None)

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("get_deal_by_id", {"deal_id": _VALID_ID})

    assert obs.success is False
    assert obs.error == "deal_not_found"


@pytest.mark.asyncio
async def test_get_deal_by_id_with_garbage_returns_not_found():
    """A malformed identifier is 'never issued', not a fault."""
    session_mock = _make_async_session_mock()

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("get_deal_by_id", {"deal_id": "not-a-uuid"})

    assert obs.success is False
    assert obs.error == "deal_not_found"
    session_mock.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_deal_by_memo_requires_memo():
    skill = _make_skill_with_session(_make_async_session_mock())
    obs = await skill.execute("get_deal_by_memo", {})

    assert obs.success is False
    assert obs.error == "memo_required"


@pytest.mark.asyncio
async def test_update_deal_status_missing_deal():
    session_mock = _make_async_session_mock()
    session_mock.execute.return_value = _scalar_mock(None)

    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute(
        "update_deal_status", {"deal_id": _VALID_ID, "status": "PAID"}
    )

    assert obs.success is False
