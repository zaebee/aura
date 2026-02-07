
import nats
import structlog
from aiogram import Bot

logger = structlog.get_logger(__name__)

class TelegramEffector:
    """
    Efferent logic: NATS Bloodstream -> External World (Telegram).
    """

    def __init__(self, nats_url: str, bot: Bot):
        self.nats_url = nats_url
        self.bot = bot
        self.nc = None

    async def start(self):
        self.nc = await nats.connect(self.nats_url)
        logger.info("effector_nats_connected", url=self.nats_url)

        # Subscribe to all hive events
        self.sub = await self.nc.subscribe("aura.hive.events.>", cb=self.handle_event)
        logger.info("effector_subscribed", subject="aura.hive.events.>")

    async def handle_event(self, msg):
        subject = msg.subject

        logger.info("effector_received_event", subject=subject)

        # TODO: Decode protobuf and notify user if chat_id is present in metadata
        # For now, let's just log it.
        # In a real scenario, the event would contain the agent_did which we could map back to a user_id.

    async def stop(self):
        if self.nc:
            await self.nc.close()
