from typing import Any
import structlog
from opentelemetry import trace
from aiogram import Bot
from src.client import GRPCNegotiationClient
from .dna import UIAction, TelegramContext, Observation

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

class TelegramConnector:
    """C - Connector: Executes UI actions and gRPC calls."""

    def __init__(self, bot: Bot, client: GRPCNegotiationClient):
        self.bot = bot
        self.client = client

    async def act(self, action: UIAction, context: TelegramContext) -> Observation:
        with tracer.start_as_current_span("connector_act") as span:
            try:
                span.set_attribute("action_type", action.action_type)
                if action.action_type == "send_message":
                    msg = await self.bot.send_message(
                        chat_id=context.chat_id,
                        text=action.text,
                        reply_markup=action.reply_markup,
                        parse_mode=action.parse_mode
                    )
                    span.set_attribute("message_id", msg.message_id)
                    return Observation(success=True, message_id=msg.message_id)
                else:
                    # Support other action types if needed
                    logger.warning("unsupported_action_type", action_type=action.action_type)
                    return Observation(success=False, error=f"Unsupported action type: {action.action_type}")
            except Exception as e:
                logger.error("failed_to_execute_action", error=str(e))
                span.record_exception(e)
                return Observation(success=False, error=str(e))

    async def call_core(self, context: TelegramContext) -> dict[str, Any]:
        with tracer.start_as_current_span("connector_call_core") as span:
            if not context.hive_context:
                return {"error": "No hive context"}

            item_id = context.hive_context.item_id
            bid_amount = context.hive_context.offer.bid_amount

            span.set_attribute("item_id", item_id)
            span.set_attribute("bid_amount", bid_amount)

            response = await self.client.negotiate(item_id, bid_amount)
            return response

    async def search_core(self, query: str) -> list[dict[str, Any]]:
        with tracer.start_as_current_span("connector_search_core") as span:
            span.set_attribute("query", query)
            results = await self.client.search(query)
            return results
