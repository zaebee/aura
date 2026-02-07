from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
)
from receptor import NegotiationStatus, TelegramReceptor

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
    message: Message, command: CommandObject, receptor: TelegramReceptor
) -> None:
    query = command.args or "hotels"
    response_text = await receptor.search(query)
    await message.answer(response_text, parse_mode="Markdown")


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
    message: Message, state: FSMContext, receptor: TelegramReceptor
) -> None:
    data = await state.get_data()
    item_id = data.get("item_id")
    bid_amount = float(message.text) if message.text else 0.0

    if not item_id:
        await message.answer("Error: No item selected. Use /search first.")
        return

    response = await receptor.negotiate(message, item_id, bid_amount)
    await message.answer(response.text, parse_mode="Markdown")

    # Clear state if negotiation is finalized
    if response.status in [NegotiationStatus.SUCCESS, NegotiationStatus.REJECTED]:
        await state.clear()


@router.callback_query(F.data == "pay_stub")
async def process_pay_stub(callback: CallbackQuery) -> None:
    await callback.answer("Payment functionality coming soon!", show_alert=True)
