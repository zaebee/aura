from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types
from src.interfaces import NegotiationProvider, NegotiationResult, SearchResult


class MockNegotiationProvider(NegotiationProvider):
    def __init__(self):
        self.search_results = []
        self.negotiation_result = {}

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return self.search_results

    async def negotiate(self, item_id: str, bid: float) -> NegotiationResult:
        return self.negotiation_result


@pytest.fixture
def mock_client():
    return MockNegotiationProvider()


@pytest.fixture
def mock_metabolism(mock_client):
    metabolism = AsyncMock()
    metabolism.connector = MagicMock()
    metabolism.connector.search_core = mock_client.search
    metabolism.execute_negotiation = AsyncMock()
    metabolism.execute_search = AsyncMock()
    return metabolism


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
