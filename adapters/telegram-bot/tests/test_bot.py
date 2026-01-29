import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.filters import CommandObject
from src.bot import cmd_start, cmd_search, process_select_hotel, process_bid, NegotiationStates

@pytest.mark.asyncio
async def test_cmd_start(message):
    await cmd_start(message)
    message.answer.assert_called()
    assert "Welcome to Aura!" in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_search_results(message, mock_client):
    command = MagicMock(spec=CommandObject)
    command.args = "Paris"

    mock_client.search_results = [
        {"item_id": "hotel_1", "name": "Hotel Alpha", "base_price": 100.0}
    ]

    await cmd_search(message, command, mock_client)

    message.answer.assert_called()
    args, kwargs = message.answer.call_args
    assert "Choose a hotel" in args[0]
    assert "reply_markup" in kwargs

    # Check if keyboard has the hotel
    keyboard = kwargs["reply_markup"].inline_keyboard
    assert len(keyboard) == 1
    assert keyboard[0][0].text == "Hotel Alpha ($100.0)"
    assert keyboard[0][0].callback_data == "select:hotel_1"

@pytest.mark.asyncio
async def test_process_select_hotel(callback_query):
    callback_query.data = "select:hotel_1"
    state = AsyncMock()

    await process_select_hotel(callback_query, state)

    state.update_data.assert_called_with(item_id="hotel_1")
    state.set_state.assert_called_with(NegotiationStates.WaitingForBid)
    callback_query.message.answer.assert_called()
    assert "hotel_1" in callback_query.message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_process_bid_accepted(message, mock_client):
    state = AsyncMock()
    state.get_data.return_value = {"item_id": "hotel_1"}
    message.text = "90"

    mock_client.negotiation_result = {
        "accepted": {
            "final_price": 90.0,
            "reservation_code": "SUCCESS123"
        }
    }

    await process_bid(message, state, mock_client)

    message.answer.assert_called()
    args, kwargs = message.answer.call_args
    assert "Deal!" in args[0]
    assert "SUCCESS123" in args[0]
    state.clear.assert_called()
