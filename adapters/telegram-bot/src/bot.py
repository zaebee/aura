from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.interfaces import NegotiationProvider

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
    message: Message, command: CommandObject, client: NegotiationProvider
) -> None:
    if not command.args:
        await message.answer("Usage: /search <query>")
        return

    results = await client.search(command.args)
    if not results:
        await message.answer("No results found or core-service unreachable. 😕")
        return

    keyboard = []
    for item in results:
        # User requirement: select:hotel_alpha
        item_id = item.get("itemId", item.get("item_id"))
        name = item.get("name", "Unknown")
        price = item.get("basePrice", item.get("base_price", 0))

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{name} (${price})", callback_data=f"select:{item_id}"
                )
            ]
        )

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer("Choose a hotel to negotiate:", reply_markup=markup)


@router.callback_query(F.data.startswith("select:"))
async def process_select_hotel(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return
    item_id = callback.data.split(":", 1)[1]

    # We don't have the item name/price here easily unless we fetch or store it.
    # For now, let's just ask.
    await state.update_data(item_id=item_id)
    await state.set_state(NegotiationStates.WaitingForBid)

    if callback.message:
        await callback.message.answer(f"Enter your bid for this item (ID: {item_id}):")
    await callback.answer()


@router.message(NegotiationStates.WaitingForBid, F.text.regexp(r"^\d+(\.\d+)?$"))
async def process_bid(
    message: Message, state: FSMContext, client: NegotiationProvider
) -> None:
    data = await state.get_data()
    item_id = str(data.get("item_id", ""))

    try:
        bid_amount = float(message.text) if message.text else 0.0
    except ValueError:
        await message.answer("Please enter a valid number.")
        return

    response = await client.negotiate(item_id, bid_amount)

    if "error" in response:
        await message.answer(str(response.get("error", "Unknown error")))
        return

    if "accepted" in response and response["accepted"] is not None:
        acc = response["accepted"]
        final_price = acc.get("finalPrice", acc.get("final_price"))
        code = acc.get("reservationCode", acc.get("reservation_code"))

        keyboard = [
            [InlineKeyboardButton(text="Pay Now (Stub)", callback_data="pay_stub")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await message.answer(
            f"✅ **Deal!**\nFinal Price: ${final_price}\nCode: `{code}`",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        await state.clear()
    elif "countered" in response and response["countered"] is not None:
        cnt = response["countered"]
        price = cnt.get("proposedPrice", cnt.get("proposed_price"))
        msg = cnt.get("humanMessage", cnt.get("human_message", ""))

        await message.answer(
            f"⚠️ **Offer: ${price}**\n"
            f"{msg}\n\n"
            "You can enter a new bid or say /search to restart.",
            parse_mode="Markdown",
        )
        # Stay in WaitingForBid state
    elif "ui_required" in response:
        await message.answer("👮 Human check needed. Please wait for an agent.")
        await state.clear()
    elif "rejected" in response:
        await message.answer("❌ Offer rejected. Try a higher bid.")
    else:
        await message.answer("Received an unknown response from Aura Core.")


@router.callback_query(F.data == "pay_stub")
async def process_pay_stub(callback: CallbackQuery) -> None:
    await callback.answer("Payment functionality coming soon!", show_alert=True)
