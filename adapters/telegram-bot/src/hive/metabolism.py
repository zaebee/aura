from typing import Any
import structlog
from opentelemetry import trace
from .aggregator import TelegramAggregator
from .transformer import TelegramTransformer
from .connector import TelegramConnector
from .generator import TelegramGenerator
from .dna import Observation

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

class TelegramMetabolism:
    """Orchestrates the ATCG flow for the Telegram Bot."""

    def __init__(
        self,
        aggregator: TelegramAggregator,
        transformer: TelegramTransformer,
        connector: TelegramConnector,
        generator: TelegramGenerator
    ):
        self.aggregator = aggregator
        self.transformer = transformer
        self.connector = connector
        self.generator = generator

    async def execute_negotiation(self, signal: Any, state_data: dict[str, Any]) -> Observation:
        with tracer.start_as_current_span("metabolism_negotiate") as span:
            logger.info("negotiation_cycle_started")

            # A - Aggregator
            context = await self.aggregator.perceive(signal, state_data)

            # T - Transformer (Initial Thinking)
            thinking_ui = await self.transformer.think(context, core_response=None)
            await self.connector.act(thinking_ui, context)

            # C - Connector (gRPC Call)
            core_response = await self.connector.call_core(context)

            # T - Transformer (Final UI)
            final_ui = await self.transformer.think(context, core_response=core_response)

            # C - Connector (Execute Final UI)
            observation = await self.connector.act(final_ui, context)

            # Enrich observation for G
            if "accepted" in core_response and core_response["accepted"]:
                observation.event_type = "deal_accepted"
                observation.metadata = {
                    "item_id": context.hive_context.item_id if context.hive_context else "",
                    "price": core_response["accepted"].get("final_price", 0),
                    "user_id": context.user_id
                }
            elif "error" in core_response:
                observation.event_type = "error"
                observation.metadata = {"error": core_response["error"], "user_id": context.user_id}

            # G - Generator
            await self.generator.pulse(observation)

            logger.info("negotiation_cycle_completed", success=observation.success)
            return observation

    async def execute_search(self, query: str, signal: Any) -> Observation:
        with tracer.start_as_current_span("metabolism_search") as span:
            logger.info("search_cycle_started", query=query)

            # A - Aggregator (perceive the search signal)
            context = await self.aggregator.perceive(signal, {})

            # C - Connector (gRPC Search)
            results = await self.connector.search_core(query)

            # T - Transformer (Build search UI)
            search_ui = await self.transformer.think(context, search_results=results)

            # C - Connector (Execute Search UI)
            observation = await self.connector.act(search_ui, context)

            # G - Generator
            observation.event_type = "user_searched"
            observation.metadata = {
                "query": query,
                "results_count": len(results),
                "user_id": context.user_id
            }

            await self.generator.pulse(observation)
            return observation
