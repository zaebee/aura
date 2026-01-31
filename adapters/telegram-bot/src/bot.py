from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
)

from src.hive.metabolism import TelegramMetabolism

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
    message: Message, command: CommandObject, metabolism: TelegramMetabolism
) -> None:
    if not command.args:
        await message.answer("Usage: /search <query>")
        return

    # Execute full ATCG search loop
    await metabolism.execute_search(command.args, message)


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
    message: Message, state: FSMContext, metabolism: TelegramMetabolism
) -> None:
    data = await state.get_data()

    # Execute full ATCG negotiation loop
    observation = await metabolism.execute_negotiation(message, data)

    if not observation.success:
        await message.answer(f"Sorry, something went wrong: {observation.error}")
        return

    if observation.event_type == "deal_accepted":
        await state.clear()


@router.callback_query(F.data == "pay_stub")
async def process_pay_stub(callback: CallbackQuery) -> None:
    await callback.answer("Payment functionality coming soon!", show_alert=True)
