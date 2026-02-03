import uuid
from typing import Any

import grpc
import structlog
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from aura_core import Observation, Skill
from google.protobuf.json_format import MessageToDict
from interfaces import NegotiationProvider, NegotiationResult, SearchResult

logger = structlog.get_logger()


class GRPCNegotiationClient(NegotiationProvider, Skill):
    def __init__(self, grpc_url: str, timeout: float = 30.0) -> None:
        self.channel = grpc.aio.insecure_channel(grpc_url)
        self.stub = negotiation_pb2_grpc.NegotiationServiceStub(self.channel)
        self.timeout = timeout

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            request = negotiation_pb2.SearchRequest(query=query, limit=limit)
            response = await self.stub.Search(request, timeout=self.timeout)
            # Use preserving_proto_field_name=True to get snake_case as per SearchResult TypedDict
            return [
                dict(MessageToDict(item, preserving_proto_field_name=True))  # type: ignore
                for item in response.results
            ]
        except grpc.RpcError as e:
            logger.error("gRPC Search failed", code=e.code(), details=e.details())
            return []

    async def negotiate(self, item_id: str, bid: float) -> NegotiationResult:
        try:
            request = negotiation_pb2.NegotiateRequest(
                request_id=str(uuid.uuid4()),
                item_id=item_id,
                bid_amount=bid,
                currency_code="USD",
                agent=negotiation_pb2.AgentIdentity(
                    did="did:aura:telegram-bot", reputation_score=1.0
                ),
            )
            response = await self.stub.Negotiate(request, timeout=self.timeout)
            return dict(MessageToDict(response, preserving_proto_field_name=True))  # type: ignore
        except grpc.RpcError as e:
            logger.error("gRPC Negotiate failed", code=e.code(), details=e.details())
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return {
                    "error": "Core service is currently unavailable. Please try again later."
                }
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                return {"error": "Request timed out. Please try again."}
            return {"error": f"An error occurred: {e.details()}"}

    def get_name(self) -> str:
        return "aura-core-client"

    def get_capabilities(self) -> list[str]:
        return ["search", "negotiate"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "search":
            results = await self.search(
                query=params.get("query", ""), limit=params.get("limit", 5)
            )
            return Observation(success=True, data=results)
        elif intent == "negotiate":
            res = await self.negotiate(
                item_id=params["item_id"], bid=params["bid_amount"]
            )
            return Observation(success="error" not in res, data=res)
        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def close(self) -> None:
        await self.channel.close()
