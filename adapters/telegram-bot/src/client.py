import grpc
import uuid
import structlog
from google.protobuf.json_format import MessageToDict
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

logger = structlog.get_logger()

class AuraClient:
    def __init__(self, grpc_url: str):
        self.channel = grpc.aio.insecure_channel(grpc_url)
        self.stub = negotiation_pb2_grpc.NegotiationServiceStub(self.channel)

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        try:
            request = negotiation_pb2.SearchRequest(query=query, limit=limit)
            response = await self.stub.Search(request, timeout=5.0)
            return [MessageToDict(item) for item in response.results]
        except grpc.RpcError as e:
            logger.error("gRPC Search failed", code=e.code(), details=e.details())
            return []

    async def negotiate(self, item_id: str, bid_amount: float) -> dict:
        try:
            request = negotiation_pb2.NegotiateRequest(
                request_id=str(uuid.uuid4()),
                item_id=item_id,
                bid_amount=bid_amount,
                currency_code="USD",
                agent=negotiation_pb2.AgentIdentity(
                    did="did:aura:telegram-bot",
                    reputation_score=1.0
                )
            )
            response = await self.stub.Negotiate(request, timeout=5.0)
            return MessageToDict(response, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            logger.error("gRPC Negotiate failed", code=e.code(), details=e.details())
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return {"error": "Core service is currently unavailable. Please try again later."}
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                return {"error": "Request timed out. Please try again."}
            return {"error": f"An error occurred: {e.details()}"}

    async def close(self):
        await self.channel.close()
