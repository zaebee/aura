from typing import Any, Protocol, TypedDict


class SearchResult(TypedDict):
    item_id: str
    name: str
    base_price: float
    description_snippet: str | None


class NegotiationResult(TypedDict, total=False):
    accepted: dict[str, Any] | None
    countered: dict[str, Any] | None
    rejected: dict[str, Any] | None
    ui_required: dict[str, Any] | None
    error: str | None


class NegotiationProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search for items to negotiate."""
        ...

    async def negotiate(self, item_id: str, bid: float) -> NegotiationResult:
        """Submit a bid for an item."""
        ...
