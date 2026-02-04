from datetime import UTC, datetime
from typing import Any

import structlog
from aiogram.types import CallbackQuery, Message
from aura_core import (
    Aggregator,
    HiveContext,
    NegotiationOffer,
    SystemVitals,
    TelegramContext,
)
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramAggregator(Aggregator[Any, TelegramContext]):
    """A - Aggregator: Extracts Telegram signals into context."""

    async def get_vitals(self) -> SystemVitals:
        """Proprioception for the Telegram Bot."""
        # Simple status for now, could be expanded to check Bot API connectivity
        return SystemVitals(
            status="ok",
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def perceive(self, signal: Any, **kwargs: Any) -> TelegramContext:
        state_data = kwargs.get("state_data", {})
        with tracer.start_as_current_span("aggregator_perceive") as span:
            user_id = 0
            chat_id = 0
            text = None
            callback_data = None

            if isinstance(signal, Message):
                user_id = signal.from_user.id if signal.from_user else 0
                chat_id = signal.chat.id
                text = signal.text
                span.set_attribute("signal_type", "message")
            elif isinstance(signal, CallbackQuery):
                user_id = signal.from_user.id
                chat_id = signal.message.chat.id if signal.message else 0
                callback_data = signal.data
                span.set_attribute("signal_type", "callback_query")

            item_id = str(state_data.get("item_id", ""))
            bid_amount = 0.0
            if text and text.replace(".", "", 1).isdigit():
                bid_amount = float(text)

            # Negotiation history could be added to metadata if we had it in state_data
            history = state_data.get("history", [])

            hive_context = HiveContext(
                item_id=item_id,
                offer=NegotiationOffer(bid_amount=bid_amount),
                # system_health will be automatically injected by MetabolicLoop
                metadata={"history": history},
            )

            context = TelegramContext(
                user_id=user_id,
                chat_id=chat_id,
                hive_context=hive_context,
                message_text=text,
                callback_data=callback_data,
                fsm_data=state_data,
            )

            span.set_attribute("user_id", user_id)
            span.set_attribute("item_id", item_id)
            span.set_attribute("bid_amount", bid_amount)

            logger.info(
                "signal_perceived",
                user_id=user_id,
                item_id=item_id,
                bid_amount=bid_amount,
            )
            return context
