"""
Tests for PersistenceSkill.sanctify_wallet and is_wallet_sanctified.
Phase B: Immune System Hardening.
"""

from unittest.mock import MagicMock

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
    sessionmaker_mock = MagicMock(return_value=session_mock)
    skill.bind(settings, (sessionmaker_mock, MagicMock(), None))
    return skill


@pytest.mark.asyncio
async def test_sanctify_wallet_creates_record():
    """Upserting a new wallet creates a SanctifiedWallet record."""
    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    # No existing wallet
    session_mock.query.return_value.filter_by.return_value.first.return_value = None

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

    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.query.return_value.filter_by.return_value.first.return_value = (
        existing_wallet
    )

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
    session_mock = MagicMock()
    session_mock.__enter__ = MagicMock(return_value=session_mock)
    session_mock.__exit__ = MagicMock(return_value=False)
    session_mock.query.return_value.filter_by.return_value.first.return_value = None

    skill = _make_skill_with_session(session_mock)

    obs = await skill.execute(
        "is_wallet_sanctified",
        {"wallet_address": "0xUNKNOWN"},
    )

    assert obs.success is True
    assert obs.metadata.to_dict()["sanctified"] is False
