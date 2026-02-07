from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aura_core import Observation
from bot import (
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

    await cmd_search(message, command, mock_metabolism)

    mock_metabolism.execute.assert_called_with(message)


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
        success=True, event_type="deal_accepted"
    )

    await process_bid(message, state, mock_metabolism)

    mock_metabolism.execute.assert_called_with(
        message, state_data={"item_id": "hotel_1"}
    )
    state.clear.assert_called()
