from typing import Any
import structlog
from aiogram import Bot
from aura_core.dna import Observation, SkillProtocol

logger = structlog.get_logger(__name__)

class TelegramProtein(SkillProtocol):
    """Protein for Telegram API interactions."""

    def __init__(self, bot: Bot):
        self.bot = bot

    def get_name(self) -> str:
        return "telegram-api"

    def get_capabilities(self) -> list[str]:
        return ["send_message"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "send_message":
            try:
                msg = await self.bot.send_message(
                    chat_id=params["chat_id"],
                    text=params["text"],
                    reply_markup=params.get("reply_markup"),
                    parse_mode=params.get("parse_mode"),
                )
                return Observation(success=True, data={"message_id": msg.message_id}, message_id=msg.message_id)
            except Exception as e:
                logger.error("telegram_protein_error", error=str(e))
                return Observation(success=False, error=str(e))

        return Observation(success=False, error=f"Unknown intent: {intent}")
