from typing import Any

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from opentelemetry import trace

from .dna import TelegramContext, UIAction

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

class TelegramTransformer:
    """T - Transformer: Decides on UI actions."""

    async def think(self, context: TelegramContext, core_response: dict[str, Any] | None = None, search_results: list[dict[str, Any]] | None = None) -> UIAction:
        with tracer.start_as_current_span("transformer_think") as span:
            # Handle Search results
            if search_results is not None:
                span.set_attribute("action", "search_results")
                if not search_results:
                    return UIAction(text="No results found or core-service unreachable. 😕")

                keyboard = []
                for item in search_results:
                    item_id = item.get("item_id", item.get("itemId"))
                    name = item.get("name", "Unknown")
                    price = item.get("base_price", item.get("basePrice", 0))

                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                text=f"{name} (${price})", callback_data=f"select:{item_id}"
                            )
                        ]
                    )

                markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
                return UIAction(
                    text="Choose a hotel to negotiate:",
                    reply_markup=markup
                )

            # Handle Negotiation flow
            if core_response is None:
                span.set_attribute("action", "thinking")
                return UIAction(
                    text="⏳ Aura is thinking...",
                    show_thinking=True
                )

            span.set_attribute("core_response_present", True)

            if "error" in core_response:
                return UIAction(text=f"❌ Error: {core_response['error']}")

            if "accepted" in core_response and core_response["accepted"] is not None:
                acc = core_response["accepted"]
                final_price = acc.get("finalPrice", acc.get("final_price"))
                code = acc.get("reservationCode", acc.get("reservation_code"))

                keyboard = [[InlineKeyboardButton(text="Pay Now (Stub)", callback_data="pay_stub")]]
                markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

                return UIAction(
                    text=f"✅ **Deal!**\nFinal Price: ${final_price}\nCode: `{code}`",
                    reply_markup=markup
                )

            if "countered" in core_response and core_response["countered"] is not None:
                cnt = core_response["countered"]
                price = cnt.get("proposedPrice", cnt.get("proposed_price"))
                msg = cnt.get("humanMessage", cnt.get("human_message", ""))

                return UIAction(
                    text=f"⚠️ **Offer: ${price}**\n{msg}\n\n"
                         "You can enter a new bid or say /search to restart."
                )

            if "ui_required" in core_response:
                return UIAction(text="👮 Human check needed. Please wait for an agent.")

            if "rejected" in core_response:
                return UIAction(text="❌ Offer rejected. Try a higher bid.")

            return UIAction(text="Received an unknown response from Aura Core.")
