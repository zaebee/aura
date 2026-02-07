from typing import Any

import nats
import structlog
from aiogram import Bot
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent
from opentelemetry import trace
from translator import TelegramTranslator

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramEffector:
    """
    Effector: Handles the 'Synaptic Gap' from the Hive to Telegram.
    Subscribes to the NATS Bloodstream and notifies users.
    """

    def __init__(
        self, nats_client: nats.NATS, bot: Bot, translator: TelegramTranslator
    ):
        self.nc = nats_client
        self.bot = bot
        self.translator = translator

    async def run(self) -> None:
        """Subscribe to NATS and start the event processing loop."""
        try:
            # Subscribe to all hive events
            sub = await self.nc.subscribe("aura.hive.events.>")
            logger.info("effector_subscribed", subject="aura.hive.events.>")

            async for msg in sub.messages:
                with tracer.start_as_current_span("effector_on_event") as span:
                    span.set_attribute("subject", msg.subject)
                    await self._process_event(msg)
        except Exception as e:
            logger.error("effector_run_error", error=str(e))
            raise

    async def _process_event(self, msg: Any) -> None:
        """Process a single NATS message."""
        try:
            # 1. Parse binary proto event
            proto_event = ProtoEvent().parse(msg.data)
            logger.debug("effector_received_event", topic=proto_event.topic)

            # 2. Translate internal event to user-friendly message
            chat_id, markdown = self.translator.from_event(proto_event)

            # 3. Deliver to External World
            if chat_id and markdown:
                await self.bot.send_message(
                    chat_id=chat_id, text=markdown, parse_mode="Markdown"
                )
                logger.info(
                    "effector_notification_sent",
                    chat_id=chat_id,
                    topic=proto_event.topic,
                )

        except Exception as e:
            logger.error(
                "effector_processing_failed", subject=msg.subject, error=str(e)
            )
