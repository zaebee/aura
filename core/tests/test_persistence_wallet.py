"""
Tests for PersistenceSkill.sanctify_wallet and is_wallet_sanctified.
Phase B: Immune System Hardening.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill


def _make_skill_with_session(session_mock: MagicMock) -> PersistenceSkill:
    """Helper: returns a PersistenceSkill wired with a mock session."""
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    async_sessionmaker_mock = MagicMock(return_value=session_mock)
    skill.bind(settings, (async_sessionmaker_mock, MagicMock(), None))
    return skill


def _make_async_session_mock() -> MagicMock:
    """Async session mock: `async with` + awaitable `execute`.

    Also keeps the sync `with` protocol wired to the same mock: the old
    sync repositories run inside `to_thread` until Task 6 rewires the
    skill, so both shapes must resolve against these stubs meanwhile.
    """
    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()
    return session_mock


@pytest.mark.asyncio
async def test_sanctify_wallet_creates_record():
    """Upserting a new wallet creates a SanctifiedWallet record."""
    session_mock = _make_async_session_mock()
    # No existing wallet (both shapes: old sync query chain + new execute)
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session_mock.execute.return_value = result_mock

    skill = _make_skill_with_session(session_mock)

    obs = await skill.execute(
        "sanctify_wallet",
        {"wallet_address": "0xABC123", "asset_domain": "VEHICLE"},
    )

    assert obs.success is True
    session_mock.add.assert_called_once()
    session_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_wallet_sanctified_true():
    """Returns sanctified=True for a wallet that has been sanctified."""
    from aura_hive.hive.proteins.persistence.engine import SanctifiedWallet

    existing_wallet = MagicMock(spec=SanctifiedWallet)

    session_mock = _make_async_session_mock()
    session_mock.query.return_value.filter_by.return_value.first.return_value = (
        existing_wallet
    )
    session_mock.execute.return_value.scalar_one_or_none.return_value = existing_wallet

    skill = _make_skill_with_session(session_mock)

    obs = await skill.execute(
        "is_wallet_sanctified",
        {"wallet_address": "0xABC123"},
    )

    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is True


@pytest.mark.asyncio
async def test_is_wallet_sanctified_false():
    """Returns sanctified=False for an unknown wallet."""
    session_mock = _make_async_session_mock()
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session_mock.execute.return_value = result_mock

    skill = _make_skill_with_session(session_mock)

    obs = await skill.execute(
        "is_wallet_sanctified",
        {"wallet_address": "0xUNKNOWN"},
    )

    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is False


@pytest.mark.asyncio
async def test_is_wallet_sanctified_none_skips_the_query():
    """A None address is unsanctified by definition — no DB round-trip."""
    session_mock = _make_async_session_mock()

    skill = _make_skill_with_session(session_mock)

    obs = await skill.execute("is_wallet_sanctified", {"wallet_address": None})

    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is False
    session_mock.execute.assert_not_called()
