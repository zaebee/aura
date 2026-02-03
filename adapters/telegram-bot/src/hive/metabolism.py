from typing import Any

import structlog
from aiogram.types import Message
from aura_core import (
    Aggregator,
    Connector,
    Generator,
    MetabolicLoop,
    Observation,
    Transformer,
)
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramMetabolism(MetabolicLoop):
    """
    Orchestrates the ATCG flow for Telegram:
    Aggregator -> Connector (Core) -> Transformer -> Connector (UI) -> Generator
    """

    def __init__(
        self,
        aggregator: Aggregator[Any, Any],
        transformer: Transformer[Any, Any],
        connector: Connector[Any, Any, Any],
        generator: Generator[Any, Any],
    ):
        super().__init__(aggregator, transformer, connector, generator)
        self.aggregator: Aggregator[Any, Any] = aggregator
        self.transformer: Transformer[Any, Any] = transformer
        self.connector: Connector[Any, Any, Any] = connector
        self.generator: Generator[Any, Any] = generator

    async def execute_search(self, query: str, message: Message) -> Observation:
        """Execute a search metabolic cycle."""
        with tracer.start_as_current_span("metabolism_search") as span:
            logger.info("search_cycle_started", query=query)
            span.set_attribute("query", query)

            # A: Perceive (Get context from message)
            context = await self.aggregator.perceive(message, state_data={})

            # C: Call Core Search
            results = await self.connector.search_core(query)

            # T: Think (Decide on UI based on results)
            action = await self.transformer.think(context, search_results=results)

            # C: Act (Send Message)
            observation = await self.connector.act(action, context)

            # G: Pulse
            observation.event_type = "user_searched"
            observation.metadata = {
                "query": query,
                "results_count": len(results),
                "user_id": context.user_id,
            }
            await self.generator.pulse(observation)

            return observation

    async def execute_negotiation(
        self, signal: Any, state_data: dict[str, Any]
    ) -> Observation:
        """Execute a negotiation metabolic cycle."""
        with tracer.start_as_current_span("metabolism_negotiate") as span:
            logger.info("negotiation_cycle_started")

            # A: Perceive (Get context from message and state)
            context = await self.aggregator.perceive(signal, state_data=state_data)

            if context.hive_context:
                span.set_attribute("item_id", context.hive_context.item_id)
                span.set_attribute("bid_amount", context.hive_context.offer.bid_amount)

            # C: Call Core Negotiation
            core_result = await self.connector.call_core(context)

            # T: Think (Decide on UI based on core result)
            action = await self.transformer.think(context, core_response=core_result)

            # C: Act (Send Message)
            observation = await self.connector.act(action, context)

            # Enrich observation for G
            if "accepted" in core_result and core_result["accepted"]:
                observation.event_type = "deal_accepted"
                observation.metadata = {
                    "item_id": context.hive_context.item_id
                    if context.hive_context
                    else "",
                    "price": core_result["accepted"].get("final_price", 0),
                    "user_id": context.user_id,
                }
            elif "error" in core_result:
                observation.event_type = "error"
                observation.metadata = {
                    "error": core_result["error"],
                    "user_id": context.user_id,
                }

            # G: Pulse
            await self.generator.pulse(observation)

            return observation
