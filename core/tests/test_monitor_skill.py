import pytest
from hive.proteins.monitor.main import MonitorSkill

from config.server import ServerSettings


@pytest.mark.asyncio
async def test_monitor_skill_initialize():
    skill = MonitorSkill()
    settings = ServerSettings()
    skill.bind(settings, None)
    success = await skill.initialize()
    assert success is True
    assert skill.settings == settings

@pytest.mark.asyncio
async def test_monitor_skill_health_check():
    skill = MonitorSkill()
    obs = await skill.execute("health_check", {})
    assert obs.success is True
    assert obs.data["status"] == "healthy"

@pytest.mark.asyncio
async def test_monitor_skill_increment_counter():
    skill = MonitorSkill()
    # This should work without crashing even if prometheus is not running
    obs = await skill.execute(
        "increment_counter",
        {"name": "negotiation_total", "labels": {"service": "test"}}
    )
    assert obs.success is True
