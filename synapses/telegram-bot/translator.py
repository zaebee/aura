from typing import Any
from aiogram.types import Message, CallbackQuery
from aura_core import HiveContext, NegotiationOffer, TelegramContext
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent

class TelegramTranslator:
    @staticmethod
    def to_hive_context(message: Message, state_data: dict) -> HiveContext:
        item_id = str(state_data.get("item_id", ""))
        text = message.text
        bid_amount = 0.0
        if text and text.replace(".", "", 1).isdigit():
            bid_amount = float(text)

        history = state_data.get("history", [])

        return HiveContext(
            item_id=item_id,
            offer=NegotiationOffer(bid_amount=bid_amount),
            metadata={
                "history": history,
                "chat_id": message.chat.id,
            },
        )

    @staticmethod
    def to_telegram_context(signal: Any, state_data: dict = None) -> TelegramContext:
        state_data = state_data or {}
        user_id = 0
        chat_id = 0
        text = None
        callback_data = None

        if isinstance(signal, Message):
            user_id = signal.from_user.id if signal.from_user else 0
            chat_id = signal.chat.id
            text = signal.text
        elif isinstance(signal, CallbackQuery):
            user_id = signal.from_user.id
            chat_id = signal.message.chat.id if signal.message else 0
            callback_data = signal.data

        hive_context = None
        if isinstance(signal, Message) and state_data:
            hive_context = TelegramTranslator.to_hive_context(signal, state_data)

        return TelegramContext(
            user_id=user_id,
            chat_id=chat_id,
            hive_context=hive_context,
            message_text=text,
            callback_data=callback_data,
            fsm_data=state_data,
        )

    @staticmethod
    def from_proto_event(payload: bytes) -> ProtoEvent:
        return ProtoEvent().parse(payload)
