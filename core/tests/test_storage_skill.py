from unittest.mock import patch

import pytest
from hive.proteins.storage.main import StorageSkill

from config.database import DatabaseSettings


@pytest.mark.asyncio
async def test_storage_skill_initialize():
    skill = StorageSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )

    with patch("sqlalchemy.create_engine") as mock_create:
        success = await skill.initialize(settings)
        assert success is True
        assert skill.settings == settings
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_storage_skill_execute_unknown_intent():
    skill = StorageSkill()
    obs = await skill.execute("unknown", {})
    assert obs.success is False
    assert "Unknown intent" in obs.error
