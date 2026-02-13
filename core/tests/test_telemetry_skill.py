import pytest
from aura_core.gen.aura.core.v1 import SystemVitals
from aura_core.gen.aura.core.v1.google import protobuf
from hive.proteins.telemetry.skill import TelemetrySkill

from config.server import ServerSettings


@pytest.mark.asyncio
async def test_telemetry_skill_fetch_metrics():
    skill = TelemetrySkill()
    settings = ServerSettings(prometheus_url="http://localhost:9090")
    skill.bind(settings, None)

    obs = await skill.execute("fetch_metrics", {})
    assert obs.success is True

    vitals = SystemVitals().parse(obs.payload.value)
    assert vitals.status in ["ok", "degraded", "error", "unstable"]

@pytest.mark.asyncio
async def test_telemetry_skill_health_check():
    skill = TelemetrySkill()
    obs = await skill.execute("health_check", {})
    assert obs.success is True

    val = protobuf.StringValue().parse(obs.payload.value)
    assert val.value == "healthy"
