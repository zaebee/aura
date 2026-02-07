import uuid
from typing import Any

import grpc
import structlog
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from aura_core import Observation, SearchResult, NegotiationResult
from google.protobuf.json_format import MessageToDict

logger = structlog.get_logger()

class GRPCNegotiationClient:
    def __init__(self, core_url: str, timeout: float = 60.0):
        self.channel = grpc.aio.insecure_channel(core_url)
        self.stub = negotiation_pb2_grpc.NegotiationServiceStub(self.channel)
        self.timeout = timeout

    async def execute(self, signal: Any, **kwargs: Any) -> Observation:
        """
        Implements the Metabolism.execute() interface via gRPC.
        Maps the internal signal to gRPC requests.
        """
        # Note: This is a simplified mapping.
        # In a full implementation, we'd check if signal is for search or negotiation.

        from aura_core import TelegramContext
        if isinstance(signal, TelegramContext):
            if signal.hive_context and signal.hive_context.item_id:
                # Negotiation path
                res = await self.negotiate(
                    item_id=signal.hive_context.item_id,
                    bid=signal.hive_context.offer.bid_amount,
                    chat_id=signal.chat_id
                )
                return Observation(success="error" not in res, data=res)
            elif signal.message_text and signal.message_text.startswith("/search"):
                # Search path
                query = signal.message_text.replace("/search", "").strip()
                results = await self.search(query=query)
                return Observation(success=True, data=results)

        return Observation(success=False, error="Unsupported signal type or missing data")

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            request = negotiation_pb2.SearchRequest(query=query, limit=limit)
            response = await self.stub.Search(request, timeout=self.timeout)
            return [
                dict(MessageToDict(item, preserving_proto_field_name=True))  # type: ignore
                for item in response.results
            ]
        except grpc.RpcError as e:
            logger.error("gRPC Search failed", code=e.code(), details=e.details())
            return []

    async def negotiate(self, item_id: str, bid: float, chat_id: int = 0) -> NegotiationResult:
        try:
            request = negotiation_pb2.NegotiateRequest(
                request_id=str(uuid.uuid4()),
                item_id=item_id,
                bid_amount=bid,
                currency_code="USD",
                agent=negotiation_pb2.AgentIdentity(
                    did=f"tg:{chat_id}", reputation_score=1.0
                ),
            )
            response = await self.stub.Negotiate(request, timeout=self.timeout)
            return dict(MessageToDict(response, preserving_proto_field_name=True))  # type: ignore
        except grpc.RpcError as e:
            logger.error("gRPC Negotiate failed", code=e.code(), details=e.details())
            return {"error": str(e.details())}

    async def close(self) -> None:
        await self.channel.close()
