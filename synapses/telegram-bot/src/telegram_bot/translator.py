import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import betterproto
import structlog
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    AgentIdentity,
    NegotiationSignal,
    SearchSignal,
    Signal,
    SignalType,
    TelegramSignal,
)

from .synapse_settings import settings

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
                # Ensure query is handled as bytes first if passed (Task 2)
                query_payload = kwargs.get("query_payload")
                query_str = (
                    query_payload.decode("utf-8")
                    if isinstance(query_payload, bytes)
                    else str(command.args or "")
                )

                signal.signal_type = cast(SignalType, SignalType.SIGNAL_TYPE_SEARCH)
                signal.search = SearchSignal(
                    query=query_str,
                    limit=settings.search_limit,
                    domain=settings.default_item_domain,
                )
                signal.metadata = make_struct(
                    {
                        "chat_id": str(chat_id),
                        "user_id": str(user_id),
                        "source": "telegram",
                        "intent": "search",
                        "query": query_str,
                    }
                )
                return signal

            # Handle photo message (Hybrid Negotiation Signal)
            if kwargs.get("image_bytes"):
                image_data = kwargs["image_bytes"]
                if isinstance(image_data, bytes):
                    image_data = [image_data]

                signal.signal_type = cast(
                    SignalType, SignalType.SIGNAL_TYPE_NEGOTIATION
                )
                item_domain = str(
                    state_data.get("item_domain", settings.default_item_domain)
                )
                signal.negotiation = NegotiationSignal(
                    item_identifier=item_id,
                    item_domain=item_domain,
                    image_data=image_data,
                    mime_type="image/jpeg",
                    agent=AgentIdentity(
                        did=f"tg:{user_id}",
                        reputation_score=1.0,
                    ),
                )
                signal.metadata = make_struct(
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
            signal.metadata = make_struct(
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
            signal.metadata = make_struct(
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

        # Determine if it's an Observation or an Event and get the negotiation payload safely
        neg = None
        # Betterproto objects have which_one_of. Event has 'payload', Observation has 'data'.
        if hasattr(event, "payload"):  # Event
            name, val = betterproto.which_one_of(event, "payload")
            if name == "negotiation":
                neg = val
        elif hasattr(event, "data"):  # Observation
            name, val = betterproto.which_one_of(event, "data")
            if name == "negotiation":
                neg = val

        if neg:
            item_id = getattr(neg, "item_identifier", "")

            # Handle System Diagnosis from BeeKeeper
            if item_id == "SYSTEM_DIAGNOSIS":
                diag = metadata.get("diagnosis", "Unknown failure.")
                fix = metadata.get("fix_suggestion", "Please check logs.")
                source = metadata.get("source", "hive")
                message = (
                    f"🐝 *BEEKEEPER DIAGNOSIS* ({source})\n\n"
                    f"🚨 *Issue:* {diag}\n\n"
                    f"🛠️ *Fix Suggestion:* {fix}"
                )
                return chat_id, message, None

            # Determine action from Enum or legacy event_type
            event_type = str(getattr(event, "event_type", ""))
            action_name = ""
            if hasattr(neg, "action"):
                action_name = str(ActionType(int(neg.action)).name)

            res_name, res_val = betterproto.which_one_of(neg, "result")

            if (
                action_name == "ACTION_TYPE_ACCEPT"
                or event_type == "negotiation_accept"
            ):
                # NegotiationEvent uses .price, NegotiationObservation uses .accepted.final_price
                price = getattr(neg, "price", 0.0)
                if res_name == "accepted" and res_val:
                    price = res_val.final_price
                message = f"✅ *Deal Accepted!*\nItem: `{item_id}`\nFinal Price: `${price:.2f}`"
            elif (
                action_name == "ACTION_TYPE_COUNTER"
                or event_type == "negotiation_counter"
            ):
                price = getattr(neg, "price", 0.0)
                if res_name == "countered" and res_val:
                    price = res_val.proposed_price
                message = f"🔄 *Counter-offer Received*\nItem: `{item_id}`\nProposed Price: `${price:.2f}`\n\nWhat is your response?"
            elif (
                action_name == "ACTION_TYPE_REJECT"
                or event_type == "negotiation_reject"
            ):
                message = f"❌ *Offer Rejected*\nItem: `{item_id}`\nThe agent was not interested in your bid."
            elif (
                action_name == "ACTION_TYPE_EVALUATE"
                or event_type == "negotiation_ui_required"
            ):
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
