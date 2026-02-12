import structlog
from grpclib.client import Channel
from aura_core.gen.aura.negotiation.v1 import (
    NegotiateRequest,
    NegotiateResponse,
    NegotiationServiceStub,
)

logger = structlog.get_logger(__name__)


class GrpcAdapter:
    """
    gRPC Adapter — direct bridge between Telegram synapse and Core Hub.
    """

    def __init__(self, core_grpc_url: str):
        self.core_grpc_url = core_grpc_url
        host, port = core_grpc_url.split(":")
        self.channel = Channel(host, int(port))
        self.stub = NegotiationServiceStub(self.channel)

    async def negotiate(self, request: NegotiateRequest) -> NegotiateResponse:
        """Execute Negotiate unary call via gRPC."""
        try:
            logger.debug("grpc_sending_negotiate", request_id=request.request_id)
            # betterproto stubs use keyword arguments for fields
            response = await self.stub.negotiate(
                request_id=request.request_id,
                item_id=request.item_id,
                bid_amount=request.bid_amount,
                currency_code=request.currency_code,
                agent=request.agent,
                signal=request.signal,
            )
            logger.debug("grpc_received_negotiate_response")
            return response
        except Exception as e:
            logger.error("grpc_negotiate_failed", error=str(e))
            # Return an empty response with an error-like state if possible,
            # or let the caller handle it.
            raise

    async def close(self) -> None:
        await self.channel.close()
