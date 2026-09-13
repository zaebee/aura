"""JetStreamProvider connection lifecycle: callbacks, state, error taxonomy."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import nats.errors
import pytest
from aura_hive.hive.proteins.pulse.engine import JetStreamProvider


def _provider() -> JetStreamProvider:
    return JetStreamProvider("nats://localhost:4222")


@pytest.mark.asyncio
async def test_successful_connect_marks_tracker_connected():
    provider = _provider()
    nc = MagicMock()
    nc.jetstream.return_value = MagicMock()

    with patch(
        "aura_hive.hive.proteins.pulse.engine.nats.connect",
        new=AsyncMock(return_value=nc),
    ) as mock_connect:
        assert await provider.connect() is True

    assert provider.tracker.as_str() == "connected"
    _, kwargs = mock_connect.call_args
    assert kwargs["reconnect_time_wait"] == 2
    assert kwargs["max_reconnect_attempts"] == 60
    assert kwargs["disconnected_cb"] == provider.tracker.on_disconnected
    assert kwargs["reconnected_cb"] == provider.tracker.on_reconnected
    assert kwargs["closed_cb"] == provider.tracker.on_closed


@pytest.mark.asyncio
async def test_no_servers_leaves_tracker_disconnected():
    provider = _provider()

    with patch(
        "aura_hive.hive.proteins.pulse.engine.nats.connect",
        new=AsyncMock(side_effect=nats.errors.NoServersError),
    ):
        assert await provider.connect() is False

    assert provider.tracker.as_str() == "disconnected"


@pytest.mark.asyncio
async def test_timeout_leaves_tracker_disconnected():
    provider = _provider()

    with patch(
        "aura_hive.hive.proteins.pulse.engine.nats.connect",
        new=AsyncMock(side_effect=nats.errors.TimeoutError),
    ):
        assert await provider.connect() is False

    assert provider.tracker.as_str() == "disconnected"


@pytest.mark.asyncio
async def test_cancellation_propagates_instead_of_reporting_failure():
    provider = _provider()

    with (
        patch(
            "aura_hive.hive.proteins.pulse.engine.nats.connect",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await provider.connect()


@pytest.mark.asyncio
async def test_jetstream_failure_closes_the_open_connection():
    """connect() succeeded but jetstream() raised: no leaked socket."""
    provider = _provider()
    nc = MagicMock()
    nc.jetstream.side_effect = RuntimeError("no jetstream")
    nc.close = AsyncMock()

    with patch(
        "aura_hive.hive.proteins.pulse.engine.nats.connect",
        new=AsyncMock(return_value=nc),
    ):
        assert await provider.connect() is False

    nc.close.assert_awaited_once()
    assert provider.tracker.as_str() == "disconnected"


@pytest.mark.asyncio
async def test_typed_error_after_connect_still_closes():
    """A NoServersError arriving after connect() must not bypass cleanup."""
    provider = _provider()
    nc = MagicMock()
    nc.jetstream.side_effect = nats.errors.NoServersError
    nc.close = AsyncMock()

    with patch(
        "aura_hive.hive.proteins.pulse.engine.nats.connect",
        new=AsyncMock(return_value=nc),
    ):
        assert await provider.connect() is False

    nc.close.assert_awaited_once()
    assert provider.tracker.as_str() == "disconnected"
