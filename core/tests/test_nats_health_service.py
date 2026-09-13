"""Core NATS health over gRPC: overall pinned, state on a named service."""

import pytest
from aura_core import NatsConnectionTracker
from aura_hive.nats_health import (
    NATS_HEALTH_SERVICE,
    build_nats_health_service,
    check_trackers,
)


@pytest.mark.asyncio
async def test_empty_wiring_is_unknown_not_a_verdict():
    assert await check_trackers([]) is None


@pytest.mark.asyncio
async def test_all_connected_is_healthy():
    trackers = [NatsConnectionTracker("a"), NatsConnectionTracker("b")]
    for tracker in trackers:
        tracker.mark_connected()

    assert await check_trackers(trackers) is True


@pytest.mark.asyncio
async def test_any_drop_is_unhealthy():
    first, second = NatsConnectionTracker("a"), NatsConnectionTracker("b")
    first.mark_connected()

    assert await check_trackers([first, second]) is False


def test_service_key_names_the_nats_service():
    from aura_hive.nats_health import _NatsHealthServiceKey
    from grpclib.utils import _service_name

    assert _service_name(_NatsHealthServiceKey()) == NATS_HEALTH_SERVICE


def test_overall_stays_pinned_while_nats_has_its_own_checks():
    service = build_nats_health_service(lambda: [])
    names = set(service._checks)

    assert "" in names
    assert NATS_HEALTH_SERVICE in names
    assert service._checks[""] == set()
