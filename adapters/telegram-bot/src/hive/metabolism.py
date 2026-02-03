from typing import Any

import structlog
from aiogram.types import Message
from aura_core.dna import (
    MetabolicLoop,
    Observation,
    TelegramAggregator,
    TelegramConnector,
    TelegramGenerator,
    TelegramTransformer,
)

logger = structlog.get_logger(__name__)


class TelegramMetabolism(MetabolicLoop):
    """
    Orchestrates the ATCG flow for Telegram:
    Aggregator -> Connector (Core) -> Transformer -> Connector (UI) -> Generator
    """

    def __init__(
        self,
        aggregator: TelegramAggregator,
        transformer: TelegramTransformer,
        connector: TelegramConnector,
        generator: TelegramGenerator,
    ):
        super().__init__(aggregator, transformer, connector, generator)
        self.aggregator: TelegramAggregator = aggregator
        self.transformer: TelegramTransformer = transformer
        self.connector: TelegramConnector = connector
        self.generator: TelegramGenerator = generator

    async def execute_search(self, query: str, message: Message) -> Observation:
        """Execute a search metabolic cycle."""
        # A: Perceive (Get context from message)
        context = await self.aggregator.perceive(message, {})

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
        # A: Perceive (Get context from message and state)
        context = await self.aggregator.perceive(signal, state_data)

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
                "item_id": context.hive_context.item_id if context.hive_context else "",
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
