import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aura_core_gen.aura.core.v1 import (
    AgentIdentity,
    PerceptionSignal,
    Signal,
    SignalType,
    TelegramSignal,
)

logger = structlog.get_logger(__name__)


def sanitize_markdown(text: str) -> str:
    """Escapes backticks for safe embedding in Markdown code blocks."""
    return text.replace("`", "'")


def sanitize_callback(text: str) -> str:
    """Removes colons to prevent corruption of delimited callback data."""
    return text.replace(":", "_")


class TelegramTranslator:
    """Standardized translator for Telegram signals and events."""

    def to_signal(self, event: Any, **kwargs: Any) -> Signal:
        """
        Convert Telegram event to universal Signal protobuf.
        Maps specific Telegram interactions to Negotiation stimuli.
        """
        signal_id = str(uuid.uuid4())
        state_data = kwargs.get("state_data", {})
        item_id = str(state_data.get("item_id", ""))

        signal = Signal(
            identifier=signal_id,
            timestamp=datetime.now(UTC),
        )

        if isinstance(event, Message):
            text = event.text or ""
            user_id = event.from_user.id if event.from_user else 0
            chat_id = event.chat.id
            command = kwargs.get("command")

            if command and command.command == "search":
                signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM)
                signal.telegram = TelegramSignal(
                    user_id=user_id,
                    chat_id=chat_id,
                    message_text=text,
                )
                signal.metadata.from_dict(
                    {
                        "chat_id": str(chat_id),
                        "user_id": str(user_id),
                        "source": "telegram",
                        "intent": "search",
                        "query": str(command.args or ""),
                    }
                )
                return signal

            # Handle photo message (Perception)
            if kwargs.get("image_bytes"):
                image_data = kwargs["image_bytes"]
                if isinstance(image_data, bytes):
                    image_data = [image_data]

                signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_PERCEPTION)
                signal.perception = PerceptionSignal(
                    image_data=image_data,
                    mime_type="image/jpeg",
                    agent=AgentIdentity(
                        did=f"tg:{user_id}",
                        reputation_score=1.0,
                    ),
                )
                signal.metadata.from_dict(
                    {
                        "chat_id": str(chat_id),
                        "user_id": str(user_id),
                        "source": "telegram",
                        "item_id": item_id,
                    }
                )
                return signal

            # Standard message or bid - Use TelegramSignal for Signal Integrity
            signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM)
            signal.telegram = TelegramSignal(
                user_id=user_id,
                chat_id=chat_id,
                message_text=text,
            )
            signal.metadata.from_dict(
                {
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "source": "telegram",
                    "item_id": item_id,
                }
            )
            return signal

        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            chat_id = event.message.chat.id if event.message else 0

            signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM)
            signal.telegram = TelegramSignal(
                user_id=user_id,
                chat_id=chat_id,
                callback_data=event.data or "",
            )
            signal.metadata.from_dict(
                {
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "source": "telegram",
                }
            )
            return signal

        signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED)
        return signal

    def from_event(self, event: Any) -> tuple[int, str, Any | None]:
        """
        Convert internal NATS event to (chat_id, user-friendly markdown, optional keyboard).
        """
        metadata = getattr(event, "metadata", {})
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()

        chat_id = int(metadata.get("chat_id", "0"))

        if not chat_id:
            return 0, "", None

        message = ""
        keyboard = None

        # Observation has negotiation field
        if hasattr(event, "negotiation") and event.negotiation:
            neg = event.negotiation
            item_id = neg.item_identifier

            # Determine action from event_type
            event_type = str(getattr(event, "event_type", ""))

            if event_type == "negotiation_accept":
                price = neg.accepted.final_price if neg.accepted else 0.0
                message = f"✅ *Deal Accepted!*\nItem: `{item_id}`\nFinal Price: `${price:.2f}`"
            elif event_type == "negotiation_counter":
                price = neg.countered.proposed_price if neg.countered else 0.0
                message = f"🔄 *Counter-offer Received*\nItem: `{item_id}`\nProposed Price: `${price:.2f}`\n\nWhat is your response?"
            elif event_type == "negotiation_reject":
                message = f"❌ *Offer Rejected*\nItem: `{item_id}`\nThe agent was not interested in your bid."
            elif event_type == "negotiation_ui_required":
                # Handle Vision Report Card
                price = 0.0
                v = metadata.get("vision_result")
                # If vision_result is already a dict (from Struct), no need to json.loads
                if v:
                    try:
                        if isinstance(v, str):
                            v = json.loads(v)
                        name = sanitize_markdown(v.get("name", "Unknown Asset"))
                        color = sanitize_markdown(
                            v.get("meta", {}).get("color", "Unknown")
                        )
                        confidence = v.get("meta", {}).get("confidence", "0.0")

                        message = (
                            f"👁️ *AURA VISION REPORT*\n\n"
                            f"*Asset:* `{name}`\n"
                            f"*Color:* `{color}`\n"
                            f"*Confidence:* `{float(confidence) * 100:.1f}%`\n"
                            f"*Proposed Rent Price:* `${price:.2f}/day`\n\n"
                            f"Is this correct? Would you like to list it now?"
                        )
                        safe_item_id = sanitize_callback(item_id)
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="✅ List Now",
                                        callback_data=f"list_now:{safe_item_id}:{price}",
                                    ),
                                    InlineKeyboardButton(
                                        text="❌ Wrong Specs",
                                        callback_data=f"wrong_specs:{safe_item_id}",
                                    ),
                                ]
                            ]
                        )
                    except Exception as e:
                        message = (
                            f"⚠️ *Vision Processing Error*\nCould not parse report: {e}"
                        )
                else:
                    message = f"👤 *Human Required*\nAgent needs manual intervention for Item `{item_id}`."

        return chat_id, message, keyboard
