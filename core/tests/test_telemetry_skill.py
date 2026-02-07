import pytest
from hive.proteins.telemetry.skill import TelemetrySkill

from config.server import ServerSettings


@pytest.mark.asyncio
async def test_telemetry_skill_initialize():
    skill = TelemetrySkill()
    settings = ServerSettings()
    skill.bind(settings, None)
    success = await skill.initialize()
    assert success is True
    assert skill.settings == settings


@pytest.mark.asyncio
async def test_telemetry_skill_health_check():
    skill = TelemetrySkill()
    obs = await skill.execute("health_check", {})
    assert obs.success is True
    assert obs.data["status"] == "healthy"


@pytest.mark.asyncio
async def test_telemetry_skill_increment_counter():
    skill = TelemetrySkill()
    # This should work without crashing even if prometheus is not running
    obs = await skill.execute(
        "increment_counter",
        {"name": "negotiation_total", "labels": {"service": "test"}},
    )
    assert obs.success is True
