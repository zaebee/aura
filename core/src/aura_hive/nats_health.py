"""Core NATS state over the standard gRPC Health protocol.

The overall (`""`) service stays SERVING no matter what — readiness follows
it, and NATS state is degraded-by-design (visible, never traffic-shaping).
NATS state rides a NAMED service instead, which the gateway reads for its
`/health` details.

grpclib merges every registered check into OVERALL unless OVERALL is
passed explicitly, so the builder pins `OVERALL: []`: without that pin a
NATS drop would flip overall health and take traffic down through the
back door.
"""

from collections.abc import Callable
from typing import Any

from aura_core import NATS_HEALTH_SERVICE, NatsConnectionTracker
from grpclib.health.check import ServiceCheck
from grpclib.health.service import OVERALL, Health


class _NatsHealthServiceKey:
    """Names the service for grpclib's per-service lookup."""

    def __mapping__(self) -> dict[str, Any]:
        return {f"/{NATS_HEALTH_SERVICE}/Check": None}


async def check_trackers(trackers: list[NatsConnectionTracker]) -> bool | None:
    """True when every tracked connection is usable.

    None (UNKNOWN) while nothing is wired yet — startup, not a verdict.
    """
    if not trackers:
        return None
    return all(t.connected for t in trackers)


def build_nats_health_service(
    get_trackers: Callable[[], list[NatsConnectionTracker]],
    check_ttl: float = 5.0,
) -> Health:
    """gRPC Health service with overall pinned SERVING plus NATS state."""

    async def check_nats() -> bool | None:
        return await check_trackers(get_trackers())

    return Health(
        checks={
            OVERALL: [],
            _NatsHealthServiceKey(): [ServiceCheck(check_nats, check_ttl=check_ttl)],
        }
    )
