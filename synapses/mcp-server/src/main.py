from fastmcp import FastMCP
from .receptor import MCPReceptor
from .config import settings

mcp = FastMCP(
    name="Aura",
    version="1.0.0",
)

receptor = MCPReceptor(core_url=settings.core_url)

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
    return await receptor.search_hotels(query, limit)

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
    return await receptor.negotiate_price(item_id, bid)

@mcp.tool
def demonstrate_wallet() -> str:
    """Demonstrate the generated wallet's DID."""
    return f"🔑 Agent Wallet DID: {receptor.wallet.did}"

if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(receptor.close())
        else:
            asyncio.run(receptor.close())
