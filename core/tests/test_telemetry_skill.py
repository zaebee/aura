from unittest.mock import AsyncMock, patch

import httpx
import pytest

from config.server import ServerSettings
from hive.proteins.telemetry.skill import TelemetrySkill

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
    assert obs.metadata.to_dict()["status"] == "healthy"

@pytest.mark.asyncio
async def test_telemetry_skill_increment_counter():
    skill = TelemetrySkill()
    obs = await skill.execute(
        "increment_counter",
        {"name": "negotiation_total", "labels": {"service": "test"}},
    )
    assert obs.success is True

@pytest.mark.asyncio
@patch("hive.proteins.telemetry.engine.httpx.AsyncClient")
async def test_telemetry_skill_query_loki(mock_client_class):
    mock_client = AsyncMock()
    mock_response = httpx.Response(200, json={
        "data": {"result": [{"stream": {"job": "test"}, "values": [["123", "log line"]]}]}
    }, request=httpx.Request("GET", "http://loki"))
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    skill = TelemetrySkill()
    settings = ServerSettings(loki_url="http://loki:3100")
    skill.bind(settings, None)

    obs = await skill.execute("query_loki", {"query": '{job="test"}', "limit": 10})
    assert obs.success is True
    results = obs.metadata.to_dict()["results"]
    assert len(results) == 1
    assert results[0]["stream"]["job"] == "test"

@pytest.mark.asyncio
@patch("hive.proteins.telemetry.engine.httpx.AsyncClient")
async def test_telemetry_skill_health_check_k8s(mock_client_class):
    mock_client = AsyncMock()
    mock_response = httpx.Response(200, json={
        "status": "success",
        "data": {"result": [{"value": [0, "0"]}]}
    }, request=httpx.Request("GET", "http://prometheus"))
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    skill = TelemetrySkill()
    settings = ServerSettings(prometheus_url="http://prometheus:9090")
    skill.bind(settings, None)

    obs = await skill.execute("health_check_k8s", {"namespace": "default"})
    assert obs.success is True
    data = obs.metadata.to_dict()
    assert data["status"] == "healthy"
    assert data["unhealthy_pods_count"] == 0
