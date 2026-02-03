

import structlog
from aura_core import (
    Connector,
    NegotiationResult,
    Observation,
    SearchResult,
    TelegramContext,
    UIAction,
)
from opentelemetry import trace

from .proteins.aura_client import GRPCNegotiationClient
from .proteins.telegram_api import TelegramProtein

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramConnector(Connector[UIAction, Observation, TelegramContext]):
    """C - Connector: Executes UI actions and gRPC calls via Proteins."""

    def __init__(self, telegram: TelegramProtein, aura: GRPCNegotiationClient):
        self.telegram = telegram
        self.aura = aura

    async def act(self, action: UIAction, context: TelegramContext) -> Observation:
        with tracer.start_as_current_span("connector_act") as span:
            span.set_attribute("action_type", action.action_type)
            if action.action_type == "send_message":
                params = {
                    "chat_id": context.chat_id,
                    "text": action.text,
                    "reply_markup": action.reply_markup,
                    "parse_mode": action.parse_mode,
                }
                return await self.telegram.execute("send_message", params)

            return Observation(
                success=False, error=f"Unsupported action type: {action.action_type}"
            )

    async def call_core(self, context: TelegramContext) -> NegotiationResult:
        if not context.hive_context:
            return {"error": "No hive context"}

        obs = await self.aura.execute(
            "negotiate",
            {
                "item_id": context.hive_context.item_id,
                "bid_amount": context.hive_context.offer.bid_amount,
            },
        )
        if obs.success:
            return obs.data  # type: ignore
        return {"error": obs.error}

    async def search_core(self, query: str) -> list[SearchResult]:
        obs = await self.aura.execute("search", {"query": query})
        if obs.success:
            return obs.data  # type: ignore
        return []
