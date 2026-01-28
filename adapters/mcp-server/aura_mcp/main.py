"""Aura MCP tools."""

from fastmcp import FastMCP
from fastmcp.tools import tool

from server import AuraMCPServer


mcp = FastMCP(
    name="Aura",
    version="1.0.0",
)


server = AuraMCPServer()


@mcp.tool
async def search_hotels(query: str, limit: int = 3) -> str:
    """
    Search hotels via Aura Gateway.

    Args:
        query: Search query string
        limit: Maximum number of results (default: 3)

    Returns:
        Formatted string with search results for LLM consumption
    """
    return await server.search_hotels(query, limit)


@mcp.tool
async def negotiate_price(item_id: str, bid: float) -> str:
    """
    Negotiate price for an item via Aura Gateway.

    Args:
        item_id: ID of the item to negotiate
        bid: Bid amount in USD

    Returns:
        Formatted string with negotiation result for LLM consumption
    """
    return await server.negotiate_price(item_id, bid)


@mcp.tool
def demonstrate_wallet() -> str:
    """Demonstrate the generated wallet's DID."""
    return f"🔑 Agent Wallet DID: {self.wallet.did}"


def main():
    # mcp.tool(server.search_hotels)
    # mcp.tool(server.negotiate_price)
    mcp.run()


if __name__ == "__main__":
    main()
    # mcp.run()
