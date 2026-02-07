from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
)
from typing import Any
from translator import TelegramTranslator

router = Router()

class NegotiationStates(StatesGroup):
    WaitingForBid = State()

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Welcome to Aura! 🤖\n"
        "I can help you find hotels and negotiate the best prices.\n"
        "Use /search <destination> to start."
    )

@router.message(Command("search"))
async def cmd_search(
    message: Message, command: CommandObject, metabolism: Any
) -> None:
    # Receptor translates and calls metabolism
    signal = TelegramTranslator.to_telegram_context(message)
    observation = await metabolism.execute(signal)

    if observation.success and observation.data:
        results = observation.data
        if not results:
            await message.answer("No hotels found matching your criteria.")
            return

        response = "🏨 Search Results:\n\n"
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        for item in results:
            name = item.get("name", "Unknown")
            price = item.get("base_price", 0.0)
            item_id = item.get("item_id", "unknown")
            response += f"• {name} - ${price:.2f}\n"
            builder.button(text=f"Select {name}", callback_data=f"select:{item_id}")

        builder.adjust(1)
        await message.answer(response, reply_markup=builder.as_markup())
    else:
        await message.answer(f"Search failed: {observation.error}")

@router.callback_query(F.data.startswith("select:"))
async def process_select_hotel(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return
    item_id = callback.data.split(":", 1)[1]

    await state.update_data(item_id=item_id)
    await state.set_state(NegotiationStates.WaitingForBid)

    if callback.message:
        await callback.message.answer(f"Enter your bid for this item (ID: {item_id}):")
    await callback.answer()

@router.message(NegotiationStates.WaitingForBid, F.text.regexp(r"^\d+(\.\d+)?$"))
async def process_bid(
    message: Message, state: FSMContext, metabolism: Any
) -> None:
    data = await state.get_data()

    # Receptor translates and calls metabolism
    # Note: In the new pattern, the Receptor might directly use the Translator
    # to form a Signal, but for now we'll keep calling metabolism.execute(message)
    # as the Aggregator inside the core will handle the translation if needed,
    # OR we translate here and send a clean Signal.

    # According to the directive: "It must receive an external event ...,
    # use translator.py to convert it into an aura_core.types.Signal,
    # and call the MetabolicLoop.execute()"

    signal = TelegramTranslator.to_telegram_context(message, state_data=data)
    observation = await metabolism.execute(signal)

    if not observation.success:
        await message.answer(f"Sorry, something went wrong: {observation.error}")
        return

    # Handle immediate response
    res = observation.data or {}
    if "accepted" in res and res["accepted"]:
        data = res["accepted"]
        await message.answer(f"🎉 ACCEPTED! Final Price: ${data['final_price']:.2f}")
        await state.clear()
    elif "countered" in res and res["countered"]:
        data = res["countered"]
        await message.answer(f"🔄 COUNTER-OFFER: ${data['proposed_price']:.2f}\n{data['human_message']}")
    elif "rejected" in res and res["rejected"]:
        await message.answer("🚫 REJECTED")
        await state.clear()
    elif "ui_required" in res and res["ui_required"]:
        await message.answer("🚨 HUMAN INTERVENTION REQUIRED")

@router.callback_query(F.data == "pay_stub")
async def process_pay_stub(callback: CallbackQuery) -> None:
    await callback.answer("Payment functionality coming soon!", show_alert=True)
