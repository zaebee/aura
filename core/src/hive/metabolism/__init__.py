from typing import Any

import structlog
from aura_core import (
    Aggregator,
    Connector,
    Generator,
    HiveContext,
    IntentAction,
    Membrane,
    Observation,
    Transformer,
)
from aura_core import (
    MetabolicLoop as BaseMetabolicLoop,
)
from opentelemetry import trace

from .metrics import heartbeat_total, negotiation_accepted_total, negotiation_total

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MetabolicLoop(
    BaseMetabolicLoop[Any, HiveContext, IntentAction, Observation, Any]
):
    """
    Orchestrates the ATCG flow with core-specific telemetry:
    Signal -> Membrane(In) -> Aggregator -> Transformer -> Membrane(Out) -> Connector -> Generator
    """

    def __init__(
        self,
        aggregator: Aggregator[Any, HiveContext],
        transformer: Transformer[HiveContext, IntentAction],
        connector: Connector[IntentAction, Observation, HiveContext],
        generator: Generator[Observation, Any],
        membrane: Membrane[Any, IntentAction, HiveContext],
    ):
        super().__init__(aggregator, transformer, connector, generator, membrane)

    async def execute(self, signal: Any, **kwargs: Any) -> Any:
        """
        Execute one full metabolic cycle.
        """
        negotiation_total.labels(service="core").inc()
        is_heartbeat = kwargs.get("is_heartbeat", False)
        if is_heartbeat:
            heartbeat_total.labels(service="core").inc()

        logger.info("metabolism_cycle_started")

        observation = await super().execute(signal, **kwargs)

        if is_heartbeat:
            observation.metadata["is_heartbeat"] = True

        if observation.success and observation.event_type == "negotiation_accept":
            negotiation_accepted_total.labels(service="core").inc()

        logger.info(
            "metabolism_cycle_completed",
            success=observation.success,
        )

        return observation
