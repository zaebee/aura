from unittest.mock import MagicMock

import pytest
from hive.proteins.persistence.skill import PersistenceSkill

from config.database import DatabaseSettings


@pytest.mark.asyncio
async def test_persistence_skill_initialize() -> None:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    mock_sessionmaker = MagicMock()
    mock_engine = MagicMock()

    skill.bind(settings, (mock_sessionmaker, mock_engine))
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
    skill.bind(settings, (MagicMock(), MagicMock()))
    obs = await skill.execute("unknown", {})
    assert obs.success is False
    assert "Unknown intent" in obs.error
