import pytest
from unittest.mock import AsyncMock
from hive.proteins.pulse.main import PulseSkill
from config.server import ServerSettings

@pytest.mark.asyncio
async def test_pulse_skill_initialize(mocker):
    skill = PulseSkill()
    mock_provider = mocker.patch("hive.proteins.pulse.main.NatsProvider").return_value
    mock_provider.connect = AsyncMock(return_value=True)

    success = await skill.initialize(ServerSettings())
    assert success is True

@pytest.mark.asyncio
async def test_pulse_skill_execute_not_initialized():
    skill = PulseSkill()
    obs = await skill.execute("emit_heartbeat", {})
    assert obs.success is False
    assert "not_initialized" in obs.error
