"""NatsConnectionTracker: one state word for every NATS socket."""

import pytest
from aura_core import NatsConnectionTracker


@pytest.mark.asyncio
async def test_starts_disconnected_before_first_connect():
    tracker = NatsConnectionTracker("probe")
    assert tracker.as_str() == "disconnected"
    assert tracker.connected is False


@pytest.mark.asyncio
async def test_full_lifecycle_through_the_nats_callbacks():
    tracker = NatsConnectionTracker("probe")

    tracker.mark_connected()
    assert tracker.as_str() == "connected"
    assert tracker.connected is True

    await tracker.on_disconnected()
    assert tracker.as_str() == "disconnected"
    assert tracker.connected is False

    await tracker.on_reconnected()
    assert tracker.as_str() == "connected"

    await tracker.on_closed()
    assert tracker.as_str() == "closed"
    assert tracker.connected is False


@pytest.mark.asyncio
async def test_repeated_callback_does_not_relog_or_change_state():
    from structlog.testing import capture_logs

    tracker = NatsConnectionTracker("probe")
    tracker.mark_connected()

    with capture_logs() as logs:
        await tracker.on_reconnected()

    assert tracker.as_str() == "connected"
    assert [log for log in logs if log.get("event") == "nats_connection_state"] == []
