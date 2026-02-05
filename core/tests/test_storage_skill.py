from unittest.mock import MagicMock

import pytest
from hive.proteins.storage.main import StorageSkill

from config.database import DatabaseSettings


@pytest.mark.asyncio
async def test_storage_skill_initialize():
    skill = StorageSkill()
    settings = DatabaseSettings(url="postgresql://user:password@localhost:5432/aura_db")
    mock_sessionmaker = MagicMock()
    mock_engine = MagicMock()

    skill.bind(settings, (mock_sessionmaker, mock_engine))
    success = await skill.initialize()
    assert success is True
    assert skill.settings == settings

@pytest.mark.asyncio
async def test_storage_skill_execute_unknown_intent():
    skill = StorageSkill()
    settings = DatabaseSettings(url="postgresql://user:password@localhost:5432/aura_db")
    skill.bind(settings, (MagicMock(), MagicMock()))
    obs = await skill.execute("unknown", {})
    assert obs.success is False
    assert "Unknown intent" in obs.error
