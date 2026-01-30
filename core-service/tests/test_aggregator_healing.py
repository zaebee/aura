import pytest
import httpx
from unittest.mock import MagicMock, AsyncMock
from hive.aggregator import HiveAggregator

@pytest.mark.asyncio
async def test_aggregator_healing_on_prometheus_timeout(mocker):
    """
    Verify that the Aggregator returns UNKNOWN status when Prometheus times out.
    """
    aggregator = HiveAggregator()
    mocker.patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout!"))
    metrics = await aggregator.get_system_metrics()
    assert metrics["status"] == "UNKNOWN"
    assert "Timeout!" in metrics["error"]

@pytest.mark.asyncio
async def test_aggregator_healing_on_prometheus_connection_error(mocker):
    """
    Verify that the Aggregator returns UNKNOWN status on connection error.
    """
    aggregator = HiveAggregator()
    mocker.patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused"))
    metrics = await aggregator.get_system_metrics()
    assert metrics["status"] == "UNKNOWN"
    assert "Connection refused" in metrics["error"]

@pytest.mark.asyncio
async def test_aggregator_healing_with_cache_fallback(mocker):
    """
    Verify that the Aggregator returns cached data even if Prometheus fails.
    """
    aggregator = HiveAggregator()

    # 1. Prime the cache
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "data": {"result": [{"value": [0, "42.0"]}]}
    }

    # Correctly patch AsyncClient.get
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    mock_get.return_value = mock_response

    # First call to fill cache
    res1 = await aggregator.get_system_metrics()
    assert res1["cpu_usage_percent"] == 42.0
    assert res1["cached"] is False

    # 2. Mock failure for second call
    mock_get.side_effect = httpx.ConnectError("Failed now")

    # Manually expire the cache to trigger fetch and then failure
    aggregator._metrics_cache._timestamp = 0

    metrics = await aggregator.get_system_metrics()

    # Should return cached data from the except block
    assert metrics["cpu_usage_percent"] == 42.0
    assert metrics["cached"] is True
    assert metrics["warning"] == "stale_data"
