import grpc
import structlog
from aura_core.gen.aura.negotiation.v1 import NegotiationServiceStub

from .translator import TelegramTranslator

logger = structlog.get_logger(__name__)

class TelegramReceptor:
    """
    Afferent logic: External World (Telegram) -> Metabolism (Core gRPC).
    """

    def __init__(self, core_url: str):
        self.channel = grpc.aio.insecure_channel(core_url)
        self.stub = NegotiationServiceStub(self.channel)

    async def negotiate(self, message, item_id: str, bid_amount: float):
        request = TelegramTranslator.to_negotiate_request(message, item_id, bid_amount)
        try:
            response = await self.stub.negotiate(request)
            return TelegramTranslator.from_negotiate_response(response)
        except Exception as e:
            logger.error("receptor_negotiate_error", error=str(e))
            return f"Error connecting to Core: {e}"

    async def search(self, query: str, limit: int = 5):
        request = TelegramTranslator.to_search_request(query, limit)
        try:
            response = await self.stub.search(request)
            return TelegramTranslator.from_search_response(response)
        except Exception as e:
            logger.error("receptor_search_error", error=str(e))
            return f"Error connecting to Core: {e}"

    async def close(self):
        await self.channel.close()
