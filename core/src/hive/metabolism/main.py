from typing import Any

import numpy as np
import structlog
from aura_core import (
    Aggregator,
    Connector,
    Generator,
    Membrane,
    SkillRegistry,
    Transformer,
)
from aura_core import (
    MetabolicLoop as BaseMetabolicLoop,
)
from aura_core_gen.aura.core.v1 import (
    Context,
    Intent,
    Observation,
)
from opentelemetry import trace

from .errors import ApoptosisTrigger, GeometricCeilingError
from .holonom_v3 import HolonomV3

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MetabolicLoop(BaseMetabolicLoop[Any, Context, Intent, Observation, Any]):
    """
    Orchestrates the ATCG flow with core-specific monitoring via Telemetry Protein.
    Pure Pipe: Signal -> A -> T -> M -> C -> G.
    Now integrated with Holonom v3.0 (ASDLEOU) and DNA Binary Bloodstream.
    """

    def __init__(
        self,
        aggregator: Aggregator[Any, Context],
        transformer: Transformer[Context, Intent],
        connector: Connector[Intent, Observation, Context],
        generator: Generator[Observation, Any],
        membrane: Membrane[Any, Intent, Context],
        registry: SkillRegistry | None = None,
    ):
        super().__init__(aggregator, transformer, connector, generator, membrane)
        self.registry = registry
        # Initialize Holonom v3.0 Core
        self.holonom = HolonomV3()

    async def execute(self, signal: Any, **kwargs: Any) -> Observation:
        """
        Execute one full metabolic cycle.
        Pure implementation: Signal -> A -> T -> C -> G (with Membrane guards).
        """
        if self.registry:
            await self.registry.execute(
                "telemetry",
                "increment_counter",
                {"name": "negotiation_total", "labels": {"service": "core"}},
            )

        logger.info("metabolism_cycle_started", version="v4.0")
        self.holonom.reset_recursion()

        try:
            with tracer.start_as_current_span("metabolic_loop"):
                # 1. Inbound Membrane
                if self.membrane and hasattr(self.membrane, "inspect_inbound"):
                    signal = await self.membrane.inspect_inbound(signal)

                # 2. Aggregator (A) - Perceives Signal + Internal State (Vitals)
                # Aggregator handles parsing of binary signals from NATS
                context = await self.aggregator.perceive(signal, **kwargs)

                # 7D Perception Step (ASDLEOU)
                vitals = await self.aggregator.get_vitals()

                # Derive 7D signals from context and vitals
                meta = context.metadata.to_dict() if hasattr(context.metadata, "to_dict") else {}

                # Heuristic derivation for MSFS phase
                # A: Articulation (input volume)
                articulation = min(1.0, len(str(signal)) / 2000.0)
                # D: Dynamics (reputation or activity)
                dynamics = float(meta.get("reputation", 0.5))

                mock_7d_signals = np.array(
                    [
                        articulation,                       # A: Articulation
                        vitals.cpu_usage_percent / 100.0,   # S: Structure
                        dynamics,                           # D: Dynamics
                        0.1,                                # L: Logic (base coherence)
                        0.0,                                # E: Interiority (updated during Reasoning)
                        vitals.memory_usage_mb / 1024.0,    # O: Foundation
                        0.5,                                # U: Unity
                    ]
                )

                # 3. Transformer (T) - Reasoning
                # Track self-modeling recursion
                self.holonom.track_self_modeling(1)
                decision = await self.transformer.think(context, **kwargs)

                # Update Holonom with Interiority (E) from reasoning
                interiority_gain = 0.1 if decision.action != 0 else -0.05
                stats = self.holonom.step(interiority_gain, mock_7d_signals)
                logger.info("holonom_v3_step", **stats)

                # 4. Outbound Membrane - Deterministic Guards
                if self.membrane and hasattr(self.membrane, "inspect_outbound"):
                    decision = await self.membrane.inspect_outbound(decision, context)

                # 5. Connector (C) - Physical Action
                observation = await self.connector.act(decision, context)

                # 6. Generator (G) - Event Emission
                await self.generator.pulse(observation)

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
                purity=stats["purity"],
            )

            return observation

        except (GeometricCeilingError, ApoptosisTrigger) as e:
            logger.critical("holonom_metabolic_failure", error=str(e))
            # Emergency fallback / Alert
            if self.registry:
                await self.registry.execute(
                    "pulse",
                    "emit_alert",
                    {"message": f"HOLONOM_CRITICAL: {str(e)}", "severity": "CRITICAL"},
                )
            return Observation(success=False, error=str(e))
        except Exception as e:
            logger.error("metabolic_failure", error=str(e), exc_info=True)
            raise e
