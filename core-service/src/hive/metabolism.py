from typing import Any

import structlog
from hive.dna import Aggregator, Connector, Generator, Membrane, Transformer
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MetabolicLoop:
    """
    Orchestrates the ATCG flow:
    Signal -> Membrane(In) -> Aggregator -> Transformer -> Membrane(Out) -> Connector -> Generator
    """

    def __init__(
        self,
        aggregator: Aggregator,
        transformer: Transformer,
        connector: Connector,
        generator: Generator,
        membrane: Membrane,
    ):
        self.aggregator = aggregator
        self.transformer = transformer
        self.connector = connector
        self.generator = generator
        self.membrane = membrane

    async def execute(self, signal: Any) -> Any:
        """
        Execute one full metabolic cycle.
        """
        with tracer.start_as_current_span("hive_metabolism") as span:
            logger.info("metabolism_cycle_started")

            # 1. Membrane (Inbound) - Filter/Sanitize
            with tracer.start_as_current_span("nucleotide_membrane_in"):
                signal = await self.membrane.inspect_inbound(signal)

            # 2. Aggregator (A) - Perceive/Sense
            with tracer.start_as_current_span("nucleotide_aggregator") as a_span:
                context = await self.aggregator.perceive(signal)
                a_span.set_attribute("item_id", context.item_id)
                a_span.set_attribute("bid_amount", context.bid_amount)
                span.set_attribute("item_id", context.item_id)

            # 3. Transformer (T) - Think/Reason
            with tracer.start_as_current_span("nucleotide_transformer") as t_span:
                decision = await self.transformer.think(context)
                t_span.set_attribute("action", decision.action)
                t_span.set_attribute("price", decision.price)

            # 4. Membrane (Outbound) - Guard/Verify
            with tracer.start_as_current_span("nucleotide_membrane_out") as m_out_span:
                safe_decision = await self.membrane.inspect_outbound(decision, context)
                if safe_decision != decision:
                    logger.info(
                        "membrane_override_applied",
                        original_price=decision.price,
                        safe_price=safe_decision.price,
                    )
                    m_out_span.set_attribute("overridden", True)

                m_out_span.set_attribute("final_action", safe_decision.action)
                m_out_span.set_attribute("final_price", safe_decision.price)

            # 5. Connector (C) - Act/Output
            with tracer.start_as_current_span("nucleotide_connector") as c_span:
                observation = await self.connector.act(safe_decision, context)
                c_span.set_attribute("success", observation.success)

            # 6. Generator (G) - Pulse/Emit
            with tracer.start_as_current_span("nucleotide_generator"):
                await self.generator.pulse(observation)

            logger.info(
                "metabolism_cycle_completed",
                action=safe_decision.action,
                price=safe_decision.price,
            )

            return observation
