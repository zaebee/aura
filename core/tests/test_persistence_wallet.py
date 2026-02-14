"""Tests for PersistenceSkill.sanctify_wallet and is_wallet_sanctified. Phase B."""

from unittest.mock import MagicMock

import pytest
from hive.proteins.persistence.skill import PersistenceSkill

from config.database import DatabaseSettings


def _make_skill_with_session(session_mock: MagicMock) -> PersistenceSkill:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    skill.bind(settings, (MagicMock(return_value=session_mock), MagicMock(), None))
    return skill


@pytest.mark.asyncio
async def test_sanctify_wallet_creates_record() -> None:
    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute(
        "sanctify_wallet", {"wallet_address": "0xABC123", "asset_domain": "VEHICLE"}
    )
    assert obs.success is True
    session_mock.add.assert_called_once()
    session_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_wallet_sanctified_true() -> None:
    from hive.proteins.persistence.engine import SanctifiedWallet

    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.query.return_value.filter_by.return_value.first.return_value = (
        MagicMock(spec=SanctifiedWallet)
    )
    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("is_wallet_sanctified", {"wallet_address": "0xABC123"})
    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is True


@pytest.mark.asyncio
async def test_is_wallet_sanctified_false() -> None:
    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.query.return_value.filter_by.return_value.first.return_value = None
    skill = _make_skill_with_session(session_mock)
    obs = await skill.execute("is_wallet_sanctified", {"wallet_address": "0xUNKNOWN"})
    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is False
