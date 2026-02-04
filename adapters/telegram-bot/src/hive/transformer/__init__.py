from typing import Any

import structlog
from aura_core import IntentAction, TelegramContext, Transformer
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramTransformer(Transformer[TelegramContext, IntentAction]):
    """T - Transformer: Decides on multi-step IntentActions."""

    async def think(
        self,
        context: TelegramContext,
        **kwargs: Any,
    ) -> IntentAction:
        with tracer.start_as_current_span("transformer_think") as span:
            # 1. Check for Search command
            if context.message_text and context.message_text.startswith("/search"):
                query = context.message_text.replace("/search", "").strip()
                if not query:
                    return IntentAction(
                        action="error",
                        price=0.0,
                        message="Please provide a search query.",
                        steps=[
                            {
                                "skill": "messenger",
                                "intent": "send_message",
                                "params": {"text": "Usage: /search <query>"},
                            }
                        ],
                    )

                span.set_attribute("action", "search")
                return IntentAction(
                    action="search",
                    price=0.0,
                    message=f"Searching for {query}",
                    steps=[
                        {
                            "skill": "core_link",
                            "intent": "search",
                            "params": {"query": query},
                        },
                        {
                            "skill": "messenger",
                            "intent": "send_search_results",
                            "params": {},
                        },
                    ],
                )

            # 2. Check for Bid (Negotiation)
            if context.hive_context and context.hive_context.offer.bid_amount > 0:
                item_id = context.hive_context.item_id
                bid = context.hive_context.offer.bid_amount
                span.set_attribute("action", "negotiate")
                return IntentAction(
                    action="negotiate",
                    price=bid,
                    message=f"Negotiating for {item_id} at ${bid}",
                    steps=[
                        {
                            "skill": "core_link",
                            "intent": "negotiate",
                            "params": {"item_id": item_id, "bid_amount": bid},
                        },
                        {
                            "skill": "messenger",
                            "intent": "send_negotiation_results",
                            "params": {},
                        },
                    ],
                )

            # Default: Show help or unknown
            return IntentAction(
                action="help",
                price=0.0,
                message="Show help",
                steps=[
                    {
                        "skill": "messenger",
                        "intent": "send_message",
                        "params": {
                            "text": "Welcome! Try /search <destination> or enter a bid to start negotiating."
                        },
                    }
                ],
            )
