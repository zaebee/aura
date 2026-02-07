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
    Orchestrates the ATCG flow with core-specific monitoring via Telemetry Protein.
    Pure Pipe Implementation: Logic moves into Nucleotides.
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

    async def execute(self, signal: Any, **kwargs: Any) -> Observation:
        """
        Execute one full metabolic cycle:
        Signal -> [Membrane In] -> Aggregator -> Transformer -> [Membrane Out] -> Connector -> Generator

        Purified Loop: Internal vitals collection removed; handled by Aggregator.perceive.
        """
        if self.registry:
            await self.registry.execute(
                "telemetry",
                "increment_counter",
                {"name": "negotiation_total", "labels": {"service": "core"}},
            )

        logger.info("metabolism_cycle_started")

        with tracer.start_as_current_span("metabolic_loop") as _span:
            # 1. Inbound Membrane (M-in)
            with tracer.start_as_current_span("nucleotide_membrane_in"):
                if self.membrane and hasattr(self.membrane, "inspect_inbound"):
                    signal = await self.membrane.inspect_inbound(signal)

            # 2. Aggregator (A) - Pure Perception (vitals collection moved here)
            with tracer.start_as_current_span("nucleotide_aggregator"):
                context = await self.aggregator.perceive(signal, **kwargs)

            # 3. Transformer (T)
            with tracer.start_as_current_span("nucleotide_transformer"):
                decision = await self.transformer.think(context, **kwargs)

            # 4. Outbound Membrane (M-out) - Safety Guard
            with tracer.start_as_current_span("nucleotide_membrane_out"):
                if self.membrane and hasattr(self.membrane, "inspect_outbound"):
                    decision = await self.membrane.inspect_outbound(decision, context)

            # 5. Connector (C) - Action
            with tracer.start_as_current_span("nucleotide_connector"):
                observation = await self.connector.act(decision, context)

            # 6. Generator (G) - Pulse
            with tracer.start_as_current_span("nucleotide_generator"):
                await self.generator.pulse(observation)

        # Post-cycle telemetry
        if observation.success and observation.event_type == "negotiation_accept":
            if self.registry:
                await self.registry.execute(
                    "telemetry",
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
