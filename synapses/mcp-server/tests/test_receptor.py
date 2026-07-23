"""Integration tests for MCPReceptor — tool registration and wiring.

Uses FastMCP's in-memory Client to invoke the registered tools, with a mocked
MetabolicLoop so no live Hive is required.
"""

from unittest.mock import AsyncMock

import pytest
from aura_core_gen.aura.core.v1 import (
    NegotiationObservation,
    Observation,
    OfferAccepted,
    SignalType,
)
from fastmcp import Client, FastMCP

from aura_mcp.receptor import MCPReceptor
from aura_mcp.translator import MCPTranslator


def _make_receptor(observation: Observation):
    """Wire a FastMCP + real translator + a metabolism stub returning `observation`."""
    mcp = FastMCP(name="test-hive")
    metabolism = AsyncMock()
    metabolism.execute = AsyncMock(return_value=observation)
    MCPReceptor(mcp, metabolism, MCPTranslator())
    return mcp, metabolism


@pytest.mark.asyncio
async def test_tools_are_registered():
    mcp, _ = _make_receptor(Observation(success=True))
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"search_hotels", "negotiate_price"} <= names


@pytest.mark.asyncio
async def test_negotiate_price_delegates_and_formats():
    obs = Observation(
        success=True,
        negotiation=NegotiationObservation(accepted=OfferAccepted(final_price=42.0)),
    )
    mcp, metabolism = _make_receptor(obs)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "negotiate_price", {"item_id": "room-1", "bid": 50.0}
        )

    assert result.data == "🎉 SUCCESS! Negotiation accepted at $42.00."
    metabolism.execute.assert_awaited_once()
    signal = metabolism.execute.await_args.args[0]
    assert signal.signal_type == SignalType.SIGNAL_TYPE_NEGOTIATION
    assert signal.negotiation.item_identifier == "room-1"
    assert signal.negotiation.bid_amount == 50.0


@pytest.mark.asyncio
async def test_search_hotels_delegates_search_signal():
    mcp, metabolism = _make_receptor(Observation(success=True))

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_hotels", {"query": "sea view", "limit": 2}
        )

    assert "no negotiation data" in result.data
    metabolism.execute.assert_awaited_once()
    signal = metabolism.execute.await_args.args[0]
    assert signal.signal_type == SignalType.SIGNAL_TYPE_UNSPECIFIED
    meta = signal.metadata.to_dict()
    assert meta["query"] == "sea view"
    assert meta["intent"] == "search"
