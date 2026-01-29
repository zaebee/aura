import grpc
import uuid
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc


class AuraClient:
    def __init__(self, grpc_url: str):
        self.channel = grpc.aio.insecure_channel(grpc_url)
        self.stub = negotiation_pb2_grpc.NegotiationServiceStub(self.channel)

    async def search(self, query: str, limit: int = 5):
        request = negotiation_pb2.SearchRequest(query=query, limit=limit)
        response = await self.stub.Search(request)
        return response.results

    async def negotiate(self, item_id: str, bid_amount: float):
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
        return await self.stub.Negotiate(request)

    async def close(self):
        await self.channel.close()
