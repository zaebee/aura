import asyncio
import nats
import structlog
from fastmcp import FastMCP
from config import settings
from receptor import MCPReceptor
from effector import MCPEffector
from client import GRPCMetabolismClient
from wallet import AgentWallet

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger("aura-mcp-server")

mcp = FastMCP(
    name="Aura",
    version="1.0.0",
)

wallet = AgentWallet()

metabolism = GRPCMetabolismClient(core_url=settings.core_url)
receptor = MCPReceptor(metabolism, wallet)
effector = MCPEffector()

@mcp.tool
async def search_hotels(query: str, limit: int = 3) -> str:
    """
    Search hotels via Aura Platform.
    """
    return await receptor.search_hotels(query, limit)

@mcp.tool
async def negotiate_price(item_id: str, bid: float) -> str:
    """
    Negotiate price for an item via Aura Platform.
    """
    return await receptor.negotiate_price(item_id, bid)

@mcp.tool
def demonstrate_wallet() -> str:
    """Demonstrate the generated wallet's DID."""
    return f"🔑 Agent Wallet DID: {wallet.did}"

async def start():
    logger.info("🔑 Generated temporary agent wallet", did=wallet.did)

    # Initialize NATS
    try:
        nc = await nats.connect(settings.nats_url)
        logger.info("Connected to NATS", url=settings.nats_url)

        async def nats_listener():
            sub = await nc.subscribe("aura.hive.events.>")
            async for msg in sub.messages:
                await effector.emit(msg.data)

        asyncio.create_task(nats_listener())
    except Exception as e:
        logger.warning("Failed to connect to NATS", error=str(e))

    # Start the MCP server loop
    logger.info("MCP Synapse ready")
    mcp.run()

def main():
    asyncio.run(start())

if __name__ == "__main__":
    main()
