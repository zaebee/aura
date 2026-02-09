from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types


@pytest.fixture
def mock_adapter() -> AsyncMock:
    """Mock NatsAdapter for testing receptor without NATS."""
    adapter = AsyncMock()
    return adapter


@pytest.fixture
def bot() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def message(bot: AsyncMock) -> Any:
    msg = MagicMock(spec=types.Message)
    msg.bot = bot
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=123, full_name="Test User")
    msg.chat = MagicMock(id=123)
    msg.text = ""
    return msg


@pytest.fixture
def callback_query(bot: AsyncMock) -> Any:
    cb = MagicMock(spec=types.CallbackQuery)
    cb.bot = bot
    cb.message = MagicMock(spec=types.Message)
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.data = ""
    return cb
