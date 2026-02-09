from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aura_core.gen.aura.dna.v1 import Observation as ProtoObservation
from receptor import NegotiationStates, TelegramReceptor
from translator import TelegramTranslator


@pytest.fixture
def receptor(mock_adapter):
    return TelegramReceptor(mock_adapter, TelegramTranslator())


@pytest.mark.asyncio
async def test_cmd_start(message, receptor):
    await receptor.cmd_start(message)
    message.answer.assert_called()
    assert "Welcome to Aura!" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_search(message, receptor, mock_adapter):
    command = MagicMock(spec=CommandObject)
    command.command = "search"
    command.args = "Paris"

    mock_adapter.execute.return_value = ProtoObservation(success=True)

    await receptor.cmd_search(message, command)

    mock_adapter.execute.assert_called_once()


@pytest.mark.asyncio
async def test_process_select_hotel(callback_query, receptor):
    callback_query.data = "select:hotel_1"
    state = AsyncMock()

    await receptor.process_select_hotel(callback_query, state)

    state.update_data.assert_called_with(item_id="hotel_1")
    state.set_state.assert_called_with(NegotiationStates.WaitingForBid)
    callback_query.message.answer.assert_called()
    assert "hotel_1" in callback_query.message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_bid_accepted(message, receptor, mock_adapter):
    state = AsyncMock()
    state.get_data.return_value = {"item_id": "hotel_1"}
    message.text = "90"

    mock_adapter.execute.return_value = ProtoObservation(
        success=True, event_type="deal_accepted"
    )

    await receptor.process_bid(message, state)

    mock_adapter.execute.assert_called_once()
    state.clear.assert_called()


@pytest.mark.asyncio
async def test_process_bid_failed(message, receptor, mock_adapter):
    state = AsyncMock()
    state.get_data.return_value = {"item_id": "hotel_1"}
    message.text = "10"

    mock_adapter.execute.return_value = ProtoObservation(
        success=False, error="Bid too low"
    )

    await receptor.process_bid(message, state)

    mock_adapter.execute.assert_called_once()
    message.answer.assert_called()
    assert "Bid too low" in message.answer.call_args[0][0]
    state.clear.assert_not_called()
