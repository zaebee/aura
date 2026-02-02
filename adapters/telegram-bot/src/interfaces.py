from typing import Protocol

from aura_core.dna import NegotiationResult, SearchResult


class NegotiationProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search for items to negotiate."""
        ...

    async def negotiate(self, item_id: str, bid: float) -> NegotiationResult:
        """Submit a bid for an item."""
        ...
