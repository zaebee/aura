"""Pytest configuration and shared fixtures."""

import os
import sys
from pathlib import Path

import pytest

# Set required environment variables before importing any modules
os.environ.setdefault(
    "AURA_DATABASE__URL", "postgresql://test:test@localhost:5432/test_db"
)
os.environ.setdefault("AURA_LLM__API_KEY", "test-api-key")

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


class MockInventoryItem:
    """Mock inventory item for testing without database dependency."""

    def __init__(
        self,
        id: str = "test-item-1",
        name: str = "Test Room",
        base_price: float = 200.0,
        floor_price: float = 150.0,
        is_active: bool = True,
        meta: dict | None = None,
    ):
        self.id = id
        self.name = name
        self.base_price = base_price
        self.floor_price = floor_price
        self.is_active = is_active
        self.meta = meta or {}


class MockItemRepository:
    """Mock repository for testing strategies without database."""

    def __init__(self, items: dict[str, MockInventoryItem] | None = None):
        self.items = items or {}

    def get_item(self, item_id: str) -> MockInventoryItem | None:
        return self.items.get(item_id)

    def add_item(self, item: MockInventoryItem) -> None:
        self.items[item.id] = item


@pytest.fixture
def mock_item():
    """Create a standard mock inventory item."""
    return MockInventoryItem(
        id="room-101",
        name="Deluxe Suite",
        base_price=200.0,
        floor_price=150.0,
    )


@pytest.fixture
def mock_repository(mock_item):
    """Create a mock repository with a test item."""
    repo = MockItemRepository()
    repo.add_item(mock_item)
    return repo
