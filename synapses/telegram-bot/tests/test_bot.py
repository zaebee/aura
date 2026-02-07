from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aura_core import Observation
from receptor import (
    NegotiationStates,
    cmd_search,
    cmd_start,
    process_bid,
    process_select_hotel,
)


@pytest.mark.asyncio
async def test_cmd_start(message):
    await cmd_start(message)
    message.answer.assert_called()
    assert "Welcome to Aura!" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_search_results(message, mock_metabolism):
    command = MagicMock(spec=CommandObject)
    command.args = "Paris"
    message.text = "/search Paris"

    await cmd_search(message, command, mock_metabolism)

    # Verify that execute was called with a TelegramContext
    call_args = mock_metabolism.execute.call_args[0][0]
    assert call_args.chat_id == 123
    assert call_args.user_id == 123


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
async def test_process_bid_accepted(message, mock_metabolism):
    state = AsyncMock()
    state.get_data.return_value = {"item_id": "hotel_1"}
    message.text = "90"

    mock_metabolism.execute.return_value = Observation(
        success=True,
        event_type="deal_accepted",
        data={"accepted": {"final_price": 90.0}}
    )

    await process_bid(message, state, mock_metabolism)

    # Verify that execute was called with a TelegramContext
    call_args = mock_metabolism.execute.call_args[0][0]
    assert call_args.chat_id == 123
    assert call_args.hive_context.item_id == "hotel_1"
    assert call_args.hive_context.offer.bid_amount == 90.0
    state.clear.assert_called()
