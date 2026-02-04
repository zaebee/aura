from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aura_core import Observation, Skill

logger = structlog.get_logger(__name__)


class TelegramProtein(Skill):
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
        chat_id = params.get("chat_id")
        if not chat_id:
            # Try to get it from context if available
            context = params.get("_context")
            if context and hasattr(context, "chat_id"):
                chat_id = context.chat_id

        if intent == "send_message":
            if not chat_id:
                return Observation(success=False, error="chat_id is missing")
            try:
                msg = await self.bot.send_message(
                    chat_id=chat_id,
                    text=params["text"],
                    reply_markup=params.get("reply_markup"),
                    parse_mode=params.get("parse_mode"),
                )
                return Observation(
                    success=True,
                    data={"message_id": msg.message_id},
                    message_id=msg.message_id,
                )
            except Exception as e:
                logger.error("telegram_protein_error", error=str(e))
                return Observation(success=False, error=str(e))

        elif intent == "send_search_results":
            prev_obs = params.get("_previous_observation")
            search_results = prev_obs.data if prev_obs and prev_obs.success else None
            if not search_results:
                obs = await self.execute(
                    "send_message",
                    {"chat_id": chat_id, "text": "No results found. 😕"},
                )
                obs.event_type = "search_failed"
                return obs

            keyboard = []
            for item in search_results:
                item_id = item.get("item_id", item.get("itemId"))
                name = item.get("name", "Unknown")
                base_price = item.get("base_price", item.get("basePrice", 0))

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=f"{name} (${base_price})",
                            callback_data=f"select:{item_id}",
                        )
                    ]
                )

            markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            obs = await self.execute(
                "send_message",
                {
                    "chat_id": chat_id,
                    "text": "Choose a hotel to negotiate:",
                    "reply_markup": markup,
                },
            )
            obs.event_type = "user_searched"
            return obs

        elif intent == "send_negotiation_results":
            prev_obs = params.get("_previous_observation")
            if not prev_obs or not prev_obs.success:
                error_msg = (
                    prev_obs.error if prev_obs else "Negotiation failed (no response)"
                )
                return await self.execute(
                    "send_message",
                    {"chat_id": chat_id, "text": f"❌ Error: {error_msg}"},
                )

            core_response = prev_obs.data
            if not core_response:
                return await self.execute(
                    "send_message",
                    {
                        "chat_id": chat_id,
                        "text": "Received an empty response from Core.",
                    },
                )

            if "error" in core_response:
                return await self.execute(
                    "send_message",
                    {"chat_id": chat_id, "text": f"❌ Error: {core_response['error']}"},
                )

            if "accepted" in core_response and core_response["accepted"] is not None:
                acc = core_response["accepted"]
                final_price = acc.get("final_price", acc.get("finalPrice"))
                code = acc.get("reservation_code", acc.get("reservationCode"))

                keyboard = [
                    [
                        InlineKeyboardButton(
                            text="Pay Now (Stub)", callback_data="pay_stub"
                        )
                    ]
                ]
                markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

                obs = await self.execute(
                    "send_message",
                    {
                        "chat_id": chat_id,
                        "text": f"✅ **Deal!**\nFinal Price: ${final_price}\nCode: `{code}`",
                        "reply_markup": markup,
                        "parse_mode": "Markdown",
                    },
                )
                obs.event_type = "deal_accepted"
                return obs

            if "countered" in core_response and core_response["countered"] is not None:
                cnt = core_response["countered"]
                proposed_price = cnt.get("proposed_price", cnt.get("proposedPrice"))
                msg = cnt.get("human_message", cnt.get("humanMessage", ""))

                return await self.execute(
                    "send_message",
                    {
                        "chat_id": chat_id,
                        "text": f"⚠️ **Offer: ${proposed_price}**\n{msg}\n\n"
                        "You can enter a new bid or say /search to restart.",
                    },
                )

            if "ui_required" in core_response:
                return await self.execute(
                    "send_message",
                    {"chat_id": chat_id, "text": "👮 Human check needed. Please wait."},
                )

            if "rejected" in core_response:
                return await self.execute(
                    "send_message",
                    {
                        "chat_id": chat_id,
                        "text": "❌ Offer rejected. Try a higher bid.",
                    },
                )

            return await self.execute(
                "send_message",
                {"chat_id": chat_id, "text": "Received an unknown response from Core."},
            )

        return Observation(success=False, error=f"Unknown intent: {intent}")
