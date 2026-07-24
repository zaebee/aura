"""MCP synapse — Receptor (ATCG-M phase A: Aggregator).

Perceives inbound stimuli: MCP tool calls from clients (e.g. Claude) enter the
synapse here and trigger Metabolic Loop executions. This is the A phase of the
synapse mini-metabolism  receptor -> translator -> effector = A -> T -> C·G
documented in docs/ontology/patterns.yaml.
"""

from typing import cast

import structlog
from aura_core import MetabolicLoop
from fastmcp import FastMCP  # type: ignore

from .translator import MCPTranslator

logger = structlog.get_logger(__name__)


class MCPReceptor:
    """
    Receptor: Handles the 'Synaptic Gap' between MCP Clients (like Claude) and the Hive.
    Exposes tools that trigger Metabolic Loop executions.
    """

    def __init__(
        self, mcp: FastMCP, metabolism: MetabolicLoop, translator: MCPTranslator
    ):
        self.mcp = mcp
        self.metabolism = metabolism
        self.translator = translator
        self._setup_tools()

    def _setup_tools(self) -> None:
        """Register MCP tools."""

        @self.mcp.tool
        async def search_hotels(query: str, limit: int = 3) -> str:
            """
            Search hotels via Aura.
            """
            logger.info("mcp_receptor_search", query=query)
            signal = self.translator.to_signal("search", query=query, limit=limit)
            observation = await self.metabolism.execute(signal)
            return cast(str, self.translator.from_observation(observation))

        @self.mcp.tool
        async def negotiate_price(item_id: str, bid: float) -> str:
            """
            Negotiate price for an item via Aura.
            """
            logger.info("mcp_receptor_negotiate", item_id=item_id, bid=bid)
            signal = self.translator.to_signal("negotiate", item_id=item_id, bid=bid)
            observation = await self.metabolism.execute(signal)
            return cast(str, self.translator.from_observation(observation))
