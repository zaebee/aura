from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill


@pytest.mark.asyncio
async def test_persistence_skill_initialize() -> None:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_sessionmaker = MagicMock(return_value=mock_session)
    mock_engine = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    skill.bind(settings, (mock_sessionmaker, mock_engine, mock_redis))
    success = await skill.initialize()
    assert success is True
    assert skill.settings == settings


@pytest.mark.asyncio
async def test_persistence_skill_execute_unknown_intent() -> None:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    skill.bind(settings, (MagicMock(), MagicMock(), MagicMock()))
    obs = await skill.execute("unknown", {})
    assert obs.success is False
    assert "Unknown intent" in obs.error
