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
from aura_core.gen.aura.dna.v1 import (
    ActionType,
    AgentIdentity,
    Event,
    NegotiationSignal,
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

        if isinstance(event, Message):
            text = event.text or ""
            user_id = event.from_user.id if event.from_user else 0
            chat_id = event.chat.id
            command = kwargs.get("command")

            if command and command.command == "search":
                return Signal(
                    signal_id=signal_id,
                    signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM),
                    timestamp=datetime.now(UTC),
                    telegram=TelegramSignal(
                        user_id=user_id,
                        chat_id=chat_id,
                        message_text=text,
                    ),
                    metadata={
                        "chat_id": str(chat_id),
                        "user_id": str(user_id),
                        "source": "telegram",
                        "intent": "search",
                        "query": command.args or "",
                    },
                )

            # Handle photo message (Perception)
            if kwargs.get("image_bytes"):
                return Signal(
                    signal_id=signal_id,
                    signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_PERCEPTION),
                    timestamp=datetime.now(UTC),
                    perception=PerceptionSignal(
                        image_data=kwargs["image_bytes"],
                        mime_type="image/jpeg",
                        agent=AgentIdentity(
                            did=f"tg:{user_id}",
                            reputation_score=1.0,
                        ),
                    ),
                    metadata={
                        "chat_id": str(chat_id),
                        "user_id": str(user_id),
                        "source": "telegram",
                        "item_id": item_id,
                    },
                )

            # Standard message or bid - Use TelegramSignal for Signal Integrity
            return Signal(
                signal_id=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM),
                timestamp=datetime.now(UTC),
                telegram=TelegramSignal(
                    user_id=user_id,
                    chat_id=chat_id,
                    message_text=text,
                ),
                metadata={
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "source": "telegram",
                    "item_id": item_id,
                },
            )

        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            chat_id = event.message.chat.id if event.message else 0

            return Signal(
                signal_id=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_TELEGRAM),
                timestamp=datetime.now(UTC),
                telegram=TelegramSignal(
                    user_id=user_id,
                    chat_id=chat_id,
                    callback_data=event.data or "",
                ),
                metadata={
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "source": "telegram",
                },
            )

        return Signal(
            signal_id=signal_id,
            signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED),
            timestamp=datetime.now(UTC),
        )

    def from_event(self, event: Event) -> tuple[int, str, Any | None]:
        """
        Convert internal NATS event to (chat_id, user-friendly markdown, optional keyboard).
        Returns (0, "", None) if the event is not relevant to this synapse.
        """
        chat_id = int(event.metadata.get("chat_id", "0"))
        # TODO: Relying on session_token being a digit to fall back and find
        # the chat_id is fragile. This creates a tight, implicit coupling
        # between how sessions are created and how events are processed.
        # A more robust solution would be to ensure that any event destined
        # for a Telegram user explicitly includes the chat_id in its metadata.
        # This makes the contract clear and avoids potential issues
        # if the session token format changes.
        if not chat_id:
            # Try to extract from session_token if we used chat_id as session_token
            session_id = ""
            if event.negotiation:
                session_id = event.negotiation.session_token

            if session_id and session_id.isdigit():
                chat_id = int(session_id)
            else:
                return 0, "", None

        message = ""
        keyboard = None
        if event.negotiation:
            neg = event.negotiation
            action = neg.action
            price = neg.price
            item_id = neg.item_id

            if action == ActionType.ACTION_TYPE_ACCEPT:
                message = f"✅ *Deal Accepted!*\nItem: `{item_id}`\nFinal Price: `${price:.2f}`"
            elif action == ActionType.ACTION_TYPE_COUNTER:
                message = f"🔄 *Counter-offer Received*\nItem: `{item_id}`\nProposed Price: `${price:.2f}`\n\nWhat is your response?"
            elif action == ActionType.ACTION_TYPE_REJECT:
                message = f"❌ *Offer Rejected*\nItem: `{item_id}`\nThe agent was not interested in your bid."
            elif action == ActionType.ACTION_TYPE_ERROR:
                message = f"⚠️ *Negotiation Error*\nItem: `{item_id}`\nSomething went wrong during the process."
            elif action == ActionType.ACTION_TYPE_UI_REQUIRED:
                # Handle Vision Report Card
                vision_data_raw = event.metadata.get("vision_result")
                if vision_data_raw:
                    try:
                        v = json.loads(vision_data_raw)
                        # Sanitize LLM-generated strings to prevent Markdown/Injection attacks
                        name = sanitize_markdown(v.get("name", "Unknown Asset"))
                        color = sanitize_markdown(v.get("meta", {}).get("color", "Unknown"))
                        confidence = v.get("meta", {}).get("confidence", "0.0")

                        message = (
                            f"👁️ *AURA VISION REPORT*\n\n"
                            f"*Asset:* `{name}`\n"
                            f"*Color:* `{color}`\n"
                            f"*Confidence:* `{float(confidence)*100:.1f}%`\n"
                            f"*Proposed Rent Price:* `${price:.2f}/day`\n\n"
                            f"Is this correct? Would you like to list it now?"
                        )

                        # Sanitize item_id to prevent hijacking the callback_data delimiter
                        safe_item_id = sanitize_callback(item_id)

                        # Add Buttons
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
                        ])
                    except Exception as e:
                        logger.error(
                            "vision_report_card_parsing_error", error=str(e), exc_info=True
                        )
                        message = f"⚠️ *Vision Processing Error*\nCould not parse report: {e}"
                else:
                    message = f"👤 *Human Required*\nAgent needs manual intervention for Item `{item_id}`."

        return chat_id, message, keyboard
