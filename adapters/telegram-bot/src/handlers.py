from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from src.states import NegotiationStates
from src.client import AuraClient

router = Router()


class DealCallback(CallbackData, prefix="deal"):
    item_id: str


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Welcome to Aura Telegram Bot! 🤖\n\n"
        "I can help you find and negotiate deals.\n"
        "Use /search <query> to find what you're looking for."
    )


@router.message(Command("search"))
async def cmd_search(
    message: Message,
    command: CommandObject,
    client: AuraClient,
    state: FSMContext
):
    if not command.args:
        await message.answer("Please provide a search query, e.g., /search hotels in London")
        return

    results = await client.search(command.args)
    if not results:
        await message.answer("No results found. 😕")
        return

    keyboard = []
    for item in results:
        keyboard.append([InlineKeyboardButton(
            text=f"{item.name} - ${item.base_price}",
            callback_data=DealCallback(item_id=item.item_id).pack()
        )])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer("Here are some results I found:", reply_markup=markup)
    await state.set_state(NegotiationStates.searching)


@router.callback_query(DealCallback.filter())
async def process_callback_deal(
    callback: CallbackQuery,
    callback_data: DealCallback,
    state: FSMContext
):
    item_id = callback_data.item_id
    await state.update_data(item_id=item_id)
    await state.set_state(NegotiationStates.negotiating)
    await callback.message.answer(
        f"You selected item ID: {item_id}.\n"
        "What is your bid? Please enter a number."
    )
    await callback.answer()


@router.message(NegotiationStates.negotiating, F.text.regexp(r'^\d+(\.\d+)?$'))
async def process_bid(message: Message, state: FSMContext, client: AuraClient):
    data = await state.get_data()
    item_id = data.get("item_id")
    if not item_id:
        await message.answer("No active negotiation found. Please start over with /search.")
        await state.clear()
        return

    bid_amount = float(message.text)

    response = await client.negotiate(item_id, bid_amount)

    result_type = response.WhichOneof("result")

    if result_type == "accepted":
        await message.answer(
            f"✅ <b>Offer Accepted!</b>\n"
            f"Final price: ${response.accepted.final_price}\n"
            f"Reservation code: <code>{response.accepted.reservation_code}</code>",
            parse_mode="HTML"
        )
        await state.clear()
    elif result_type == "countered":
        await message.answer(
            f"⚖️ <b>Counter-offer received</b>\n"
            f"Proposed price: ${response.countered.proposed_price}\n"
            f"Message: {response.countered.human_message}\n\n"
            "Enter a new bid or /search for something else.",
            parse_mode="HTML"
        )
    elif result_type == "rejected":
        await message.answer(
            f"❌ <b>Offer Rejected</b>\n"
            f"Reason: {response.rejected.reason_code}",
            parse_mode="HTML"
        )
        await state.clear()
    elif result_type == "ui_required":
        await message.answer(
            f"ℹ️ <b>Action Required</b>\n"
            f"Please complete the process in our web interface.\n"
            f"(Template: {response.ui_required.template_id})",
            parse_mode="HTML"
        )
    else:
        await message.answer("Received an unexpected response from the server.")
