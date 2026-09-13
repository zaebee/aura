"""NatsSignalGateway connection lifecycle: callbacks, state, error taxonomy."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import nats.errors
import pytest
from aura_hive.nats_gateway import NatsSignalGateway


def _gateway() -> NatsSignalGateway:
    return NatsSignalGateway("nats://localhost:4222", metabolism=MagicMock())


@pytest.mark.asyncio
async def test_successful_start_marks_tracker_connected():
    gateway = _gateway()
    nc = MagicMock()
    nc.subscribe = AsyncMock(return_value=MagicMock())

    with patch(
        "aura_hive.nats_gateway.nats.connect", new=AsyncMock(return_value=nc)
    ) as mock_connect:
        assert await gateway.start() is True

    assert gateway.nats_state == "connected"
    _, kwargs = mock_connect.call_args
    assert kwargs["disconnected_cb"] == gateway.tracker.on_disconnected
    assert kwargs["reconnected_cb"] == gateway.tracker.on_reconnected
    assert kwargs["closed_cb"] == gateway.tracker.on_closed


@pytest.mark.asyncio
async def test_no_servers_leaves_tracker_disconnected():
    gateway = _gateway()

    with patch(
        "aura_hive.nats_gateway.nats.connect",
        new=AsyncMock(side_effect=nats.errors.NoServersError),
    ):
        assert await gateway.start() is False

    assert gateway.nats_state == "disconnected"


@pytest.mark.asyncio
async def test_cancellation_propagates_instead_of_reporting_failure():
    gateway = _gateway()

    with (
        patch(
            "aura_hive.nats_gateway.nats.connect",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await gateway.start()
