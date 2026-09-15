from typing import Any, cast

import structlog
from prometheus_client import REGISTRY, Counter

logger = structlog.get_logger(__name__)


def _get_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    """
    Idempotent registration: the default REGISTRY raises on a duplicate name,
    and tests import this module more than once.

    Defined here rather than imported from the telemetry protein: the Membrane
    is a nucleus organ and proteins sit a level below it. Four lines of
    duplication beat an upward dependency.
    """
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        # Same name, different labels is a mistake that would otherwise surface
        # far from its cause — as a ValueError inside .labels() at the first
        # intervention. Raise where the mismatch was introduced.
        registered = getattr(existing, "_labelnames", None)
        if registered is not None and tuple(registered) != tuple(labelnames):
            raise ValueError(
                f"collector {name!r} is already registered with labels "
                f"{tuple(registered)!r}, not {tuple(labelnames)!r}"
            )
        return cast(Counter, existing)
    return Counter(name, documentation, labelnames)


# Every time the guard changed or refused what the Transformer produced. This is
# the rate to watch: it measures how often free reasoning lands somewhere the
# guarantee has to catch, which is the only number that says whether the
# membrane is earning its place.
membrane_interventions_total = _get_counter(
    "membrane_interventions_total",
    "Decisions the Membrane altered, sanitised or rejected",
    ["direction", "reason"],
)


def _record_intervention(direction: str, reason: str, **fields: Any) -> None:
    """Count it and say so. An intervention that leaves no trace cannot be measured."""
    try:
        membrane_interventions_total.labels(direction=direction, reason=reason).inc()
        # Inside the try as well: **fields is caller-supplied and could fail to
        # serialise, and a crash while reporting an intervention is the same
        # failure as a crash while counting one.
        logger.warning(
            "membrane_intervention", direction=direction, reason=reason, **fields
        )
    except Exception as e:
        # Accounting must never take the guarantee down with it. The decision
        # this call accompanies has already been made and still stands; losing a
        # count degrades observability, raising here would lose the negotiation.
        logger.error(
            "membrane_metric_failed", direction=direction, reason=reason, error=str(e)
        )
