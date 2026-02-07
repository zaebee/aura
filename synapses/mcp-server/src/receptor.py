import grpc
import structlog
from aura_core.gen.aura.negotiation.v1 import NegotiationServiceStub

from .translator import MCPTranslator
from .wallet import AgentWallet

logger = structlog.get_logger(__name__)

class MCPReceptor:
    """
    Afferent logic: MCP Request -> Core gRPC.
    """

    def __init__(self, core_url: str):
        self.wallet = AgentWallet()
        self.channel = grpc.aio.insecure_channel(core_url)
        self.stub = NegotiationServiceStub(self.channel)
        logger.info("mcp_receptor_initialized", did=self.wallet.did)

    async def search_hotels(self, query: str, limit: int = 3) -> str:
        logger.info("mcp_search_hotels", query=query, limit=limit)
        request = MCPTranslator.to_search_request(query, limit)
        try:
            response = await self.stub.search(request)
            return MCPTranslator.from_search_response(response)
        except Exception as e:
            logger.error("mcp_search_error", error=str(e))
            return f"❌ Search failed: {e}"

    async def negotiate_price(self, item_id: str, bid: float) -> str:
        logger.info("mcp_negotiate_price", item_id=item_id, bid=bid)
        request = MCPTranslator.to_negotiate_request(item_id, bid, self.wallet.did)
        try:
            response = await self.stub.negotiate(request)
            return MCPTranslator.from_negotiate_response(response)
        except Exception as e:
            logger.error("mcp_negotiate_error", error=str(e))
            return f"❌ Negotiation failed: {e}"

    async def close(self):
        await self.channel.close()
