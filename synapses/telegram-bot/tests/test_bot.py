from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aura_core_gen.aura.core.v1 import Observation as ProtoObservation
from receptor import NegotiationStates, TelegramReceptor
from translator import TelegramTranslator


@pytest.fixture
def receptor(mock_adapter):
    return TelegramReceptor(mock_adapter, TelegramTranslator())


@pytest.fixture
def mock_grpc_adapter():
    return AsyncMock()


@pytest.fixture
def receptor_with_grpc(mock_adapter, mock_grpc_adapter):
    return TelegramReceptor(
        mock_adapter, TelegramTranslator(), grpc_adapter=mock_grpc_adapter
    )


@pytest.mark.asyncio
async def test_cmd_start(message, receptor):
    await receptor.cmd_start(message)
    message.answer.assert_called()
    assert "Welcome to Aura!" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_search(message, receptor, mock_adapter):
    from aura_core_gen.aura.core.v1 import SignalType

    command = MagicMock(spec=CommandObject)
    command.command = "search"
    command.args = "Paris"

    mock_adapter.execute.return_value = ProtoObservation(success=True)

    await receptor.cmd_search(message, command)

    mock_adapter.execute.assert_called_once()
    signal = mock_adapter.execute.call_args[0][0]
    assert signal.signal_type == SignalType.SIGNAL_TYPE_SEARCH
    assert signal.search.query == "Paris"


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


@pytest.mark.asyncio
async def test_process_photo(message, receptor_with_grpc, mock_grpc_adapter):
    state = AsyncMock()
    state.get_data.return_value = {}

    # Mock photo message
    photo = MagicMock()
    photo.file_id = "file_123"
    message.photo = [photo]

    # Mock bot methods
    message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="path/to/file"))
    mock_file_result = MagicMock()
    mock_file_result.read.return_value = b"fake_image_bytes"
    message.bot.download_file = AsyncMock(return_value=mock_file_result)

    # Mock gRPC response
    from aura_core_gen.aura.negotiation.v1 import NegotiateResponse, OfferCountered

    mock_response = NegotiateResponse(
        countered=OfferCountered(human_message="I see your car. My offer is $500.")
    )
    mock_grpc_adapter.negotiate.return_value = mock_response

    await receptor_with_grpc.process_photo(message, state)

    mock_grpc_adapter.negotiate.assert_called_once()
    message.answer.assert_any_call("Analyzing image... 👁️")
    message.answer.assert_any_call("I see your car. My offer is $500.")
