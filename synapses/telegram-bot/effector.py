import structlog
from aiogram import Bot
from translator import TelegramTranslator

logger = structlog.get_logger(__name__)

class TelegramEffector:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def emit(self, event_binary: bytes) -> None:
        """Processes a binary event from the NATS bloodstream and sends it to the user."""
        try:
            event = TelegramTranslator.from_proto_event(event_binary)
            logger.info("effector_received_event", topic=event.topic)

            if event.negotiation:
                message = f"Update on your negotiation for {event.negotiation.item_id}:\n"
                message += f"Action: {event.negotiation.action}\n"
                message += f"Price: ${event.negotiation.price:.2f}"

                # Extract chat_id from agent_did if it follows 'tg:<chat_id>'
                chat_id = 0
                if event.negotiation.agent_did.startswith("tg:"):
                    try:
                        chat_id = int(event.negotiation.agent_did.split(":")[1])
                    except (ValueError, IndexError):
                        logger.warning(
                            "Could not parse chat_id from agent_did",
                            agent_did=event.negotiation.agent_did,
                        )

                logger.info("effector_emitting_update", chat_id=chat_id, message=message)

                if chat_id:
                    await self.bot.send_message(chat_id, message)

        except Exception as e:
            logger.error("effector_failed_to_process_event", error=str(e))
