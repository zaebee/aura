from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types
from receptor import NegotiationStatus, StructuredResponse


@pytest.fixture
def mock_receptor():
    receptor = AsyncMock()
    receptor.search = AsyncMock(return_value="🏨 *Search Results:*")
    receptor.negotiate = AsyncMock(
        return_value=StructuredResponse(
            text="✅ *Bid Accepted!*", status=NegotiationStatus.SUCCESS
        )
    )
    return receptor


@pytest.fixture
def bot():
    return AsyncMock()


@pytest.fixture
def message(bot):
    msg = MagicMock(spec=types.Message)
    msg.bot = bot
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=123, full_name="Test User")
    msg.chat = MagicMock(id=123)
    return msg


@pytest.fixture
def callback_query(bot):
    cb = MagicMock(spec=types.CallbackQuery)
    cb.bot = bot
    cb.message = MagicMock(spec=types.Message)
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = ""
    return cb
