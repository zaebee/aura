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
    SkillRegistry,
    Transformer,
)
from aura_core import (
    MetabolicLoop as BaseMetabolicLoop,
)
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MetabolicLoop(
    BaseMetabolicLoop[Any, HiveContext, IntentAction, Observation, Any]
):
    """
    Orchestrates the ATCG flow with core-specific monitoring via Monitor Protein.
    """

    def __init__(
        self,
        aggregator: Aggregator[Any, HiveContext],
        transformer: Transformer[HiveContext, IntentAction],
        connector: Connector[IntentAction, Observation, HiveContext],
        generator: Generator[Observation, Any],
        membrane: Membrane[Any, IntentAction, HiveContext],
        registry: SkillRegistry | None = None,
    ):
        super().__init__(aggregator, transformer, connector, generator, membrane)
        self.registry = registry

    async def execute(self, signal: Any, **kwargs: Any) -> Any:
        """
        Execute one full metabolic cycle.
        """
        if self.registry:
            await self.registry.execute(
                "monitor",
                "increment_counter",
                {"name": "negotiation_total", "labels": {"service": "core"}},
            )

        logger.info("metabolism_cycle_started")

        observation = await super().execute(signal, **kwargs)

        if observation.success and observation.event_type == "negotiation_accept":
            if self.registry:
                await self.registry.execute(
                    "monitor",
                    "increment_counter",
                    {
                        "name": "negotiation_accepted_total",
                        "labels": {"service": "core"},
                    },
                )

        logger.info(
            "metabolism_cycle_completed",
            success=observation.success,
        )

        return observation
