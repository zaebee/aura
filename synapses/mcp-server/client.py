import uuid

import grpc
import structlog
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from aura_core import Observation
from google.protobuf.json_format import MessageToDict

logger = structlog.get_logger()

class GRPCMetabolismClient:
    def __init__(self, core_url: str, timeout: float = 60.0):
        self.channel = grpc.aio.insecure_channel(core_url)
        self.stub = negotiation_pb2_grpc.NegotiationServiceStub(self.channel)
        self.timeout = timeout

    async def execute_search(self, query: str, limit: int = 5) -> Observation:
        try:
            request = negotiation_pb2.SearchRequest(query=query, limit=limit)
            response = await self.stub.Search(request, timeout=self.timeout)
            data = [
                dict(MessageToDict(item, preserving_proto_field_name=True))
                for item in response.results
            ]
            return Observation(success=True, data=data)
        except grpc.RpcError as e:
            logger.error("gRPC Search failed", code=e.code(), details=e.details())
            return Observation(success=False, error=str(e.details()))

    async def execute_negotiate(self, item_id: str, bid: float, agent_did: str) -> Observation:
        try:
            request = negotiation_pb2.NegotiateRequest(
                request_id=str(uuid.uuid4()),
                item_id=item_id,
                bid_amount=bid,
                currency_code="USD",
                agent=negotiation_pb2.AgentIdentity(
                    did=agent_did, reputation_score=1.0
                ),
            )
            response = await self.stub.Negotiate(request, timeout=self.timeout)
            data = dict(MessageToDict(response, preserving_proto_field_name=True))
            return Observation(success=True, data=data)
        except grpc.RpcError as e:
            logger.error("gRPC Negotiate failed", code=e.code(), details=e.details())
            return Observation(success=False, error=str(e.details()))

    async def close(self) -> None:
        await self.channel.close()
