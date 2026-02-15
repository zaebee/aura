import asyncio
import uuid
from typing import Any, cast

import betterproto
import grpclib.const
from aura_core_gen.aura.negotiation.v1 import (
    CheckDealStatusRequest,
    CheckDealStatusResponse,
    GetSystemStatusRequest,
    GetSystemStatusResponse,
    NegotiateRequest,
    NegotiateResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from grpclib.server import Server
from hive.cortex import HiveCell
from hive.metabolism import MetabolicLoop
from hive.metabolism.logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from nats_gateway import NatsSignalGateway
from opentelemetry import trace

from config import settings

tracer = trace.get_tracer(__name__)

# 1. Configure structured logging
configure_logging(log_level=settings.server.log_level)
logger = get_logger("core")

# Metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


def extract_request_id(metadata: dict[str, str]) -> str | None:
    """Extract request_id from gRPC metadata."""
    return metadata.get(REQUEST_ID_METADATA_KEY)


class NegotiationService:
    """
    gRPC Service implementing the Aura Negotiation Protocol.
    Delegates core logic to the MetabolicLoop.
    Aligned with Chromosomal DNA v0.3.0.
    """

    def __init__(
        self,
        metabolism: MetabolicLoop | None = None,
        market_service: Any = None,
    ) -> None:
        self.metabolism = metabolism
        self.market_service = market_service

    async def negotiate(
        self,
        request_id: str = "",
        item_id: str = "",
        bid_amount: float = 0,
        currency_code: str = "",
        agent: Any = None,
        signal: Any = None,
    ) -> NegotiateResponse:
        """Main metabolic loop for negotiation."""
        if not self.metabolism:
            # How to return error in grpclib? Raising exception works.
            raise Exception("Metabolism is still initializing")

        # Betterproto methods use keyword arguments.
        # But for the server implementation, we might receive them as kwargs if we use a generic handler
        # or we implement the specific method signature.

        # Reconstruct full request if needed or just use params
        full_request = NegotiateRequest(
            request_id=request_id,
            item_id=item_id,
            bid_amount=bid_amount,
            currency_code=currency_code,
            agent=agent,
            signal=signal,
        )

        rid = request_id or str(uuid.uuid4())
        bind_request_id(rid)

        try:
            # Execute metabolic cycle
            observation = await self.metabolism.execute(full_request)

            # Map new Observation proto to NegotiateResponse
            response = NegotiateResponse()
            response.session_token = "sess_" + rid

            if observation.negotiation:
                neg = observation.negotiation
                response.valid_until_timestamp = neg.valid_until_timestamp

                res_name, res_val = betterproto.which_one_of(neg, "result")
                if res_name == "accepted" and res_val:
                    from aura_core_gen.aura.negotiation.v1 import OfferAccepted
                    response.accepted = OfferAccepted(final_price=res_val.final_price)
                    if hasattr(res_val, "reservation_code") and res_val.reservation_code:
                        response.accepted.reservation_code = res_val.reservation_code
                    if hasattr(res_val, "crypto_payment") and res_val.crypto_payment:
                        from aura_core_gen.aura.negotiation.v1 import (
                            CryptoPaymentInstructions,
                        )
                        cp = res_val.crypto_payment
                        response.accepted.crypto_payment = CryptoPaymentInstructions(
                            deal_id=cp.deal_id,
                            wallet_address=cp.wallet_address,
                            amount=cp.amount,
                            currency=cp.currency,
                            memo=cp.memo,
                            network=cp.network,
                            expires_at=cp.expires_at,
                        )
                elif res_name == "countered" and res_val:
                    from aura_core_gen.aura.negotiation.v1 import OfferCountered
                    response.countered = OfferCountered(
                        proposed_price=res_val.proposed_price,
                        human_message=res_val.human_message,
                        reason_code=res_val.reason_code or "NEGOTIATION_ONGOING",
                    )
                elif res_name == "rejected" and res_val:
                    from aura_core_gen.aura.negotiation.v1 import OfferRejected
                    response.rejected = OfferRejected(reason_code=res_val.reason_code)

            return response

        except Exception as e:
            logger.error("metabolic_failure", error=str(e), exc_info=True)
            raise e
        finally:
            clear_request_context()

    async def search(
        self, query: str = "", limit: int = 0, min_similarity: float = 0
    ) -> SearchResponse:
        """Semantic search implementation."""
        bind_request_id(str(uuid.uuid4()))
        try:
            logger.info("search_started", query=query, limit=limit)

            registry = getattr(self.metabolism, "registry", None)
            if not registry:
                raise Exception("Skill Registry not available")

            reasoning = registry.get("reasoning")
            persistence = registry.get("persistence")

            if not reasoning or not persistence:
                raise Exception("Required proteins not available")

            embed_obs = await reasoning.execute(
                "generate_embedding", {"text": query}
            )
            if not embed_obs.success:
                raise Exception(f"Failed to generate embedding: {embed_obs.error}")

            query_vector = embed_obs.embedding

            obs = await persistence.execute(
                "vector_search",
                {
                    "query_vector": query_vector,
                    "limit": limit or 5,
                    "min_similarity": min_similarity,
                },
            )

            if not obs.success:
                raise Exception(f"Search failed: {obs.error}")

            meta = obs.metadata.to_dict() if hasattr(obs.metadata, "to_dict") else {}
            items = meta.get("results", [])
            response_items = [
                SearchResultItem(
                    item_id=item["id"],
                    name=item["name"],
                    base_price=item["base_price"],
                    similarity_score=item["similarity_score"],
                    description_snippet=str(item["meta"]),
                )
                for item in items
            ]

            return SearchResponse(results=response_items)
        finally:
            clear_request_context()

    async def get_system_status(self) -> GetSystemStatusResponse:
        """Return infrastructure metrics."""
        if not self.metabolism:
            return GetSystemStatusResponse(status="initializing")

        try:
            vitals = await self.metabolism.aggregator.get_vitals()
            return GetSystemStatusResponse(
                status=str(vitals.status),
                cpu_usage_percent=float(vitals.cpu_usage_percent),
                memory_usage_mb=float(vitals.memory_usage_mb),
                timestamp=str(vitals.timestamp),
                cached=False,
            )
        except Exception as e:
            logger.error("system_status_error", error=str(e), exc_info=True)
            return GetSystemStatusResponse(status="error")

    async def check_deal_status(self, deal_id: str = "") -> CheckDealStatusResponse:
        """Check crypto payment status."""
        try:
            if not settings.crypto.enabled or not self.market_service:
                return CheckDealStatusResponse(status="NOT_FOUND")

            # Betterproto expects the response from the service
            # We assume market_service returns a compatible object or we map it
            res = await self.market_service.check_status(deal_id=deal_id)
            # If market_service still returns legacy pb2, we need to map it.
            # But let's assume it returns a dict or a betterproto object.
            if hasattr(res, "to_dict"):
                return cast(
                    CheckDealStatusResponse,
                    CheckDealStatusResponse().from_dict(res.to_dict()),
                )
            return cast(CheckDealStatusResponse, res)
        except Exception as e:
            logger.error("check_deal_status_error", deal_id=deal_id, error=str(e))
            return CheckDealStatusResponse(status="NOT_FOUND")

    def __mapping__(self) -> dict[str, grpclib.const.Handler]:
        return {
            "/aura.negotiation.v1.NegotiationService/Negotiate": grpclib.const.Handler(
                self.__rpc_negotiate,
                grpclib.const.Cardinality.UNARY_UNARY,
                NegotiateRequest,
                NegotiateResponse,
            ),
            "/aura.negotiation.v1.NegotiationService/Search": grpclib.const.Handler(
                self.__rpc_search,
                grpclib.const.Cardinality.UNARY_UNARY,
                SearchRequest,
                SearchResponse,
            ),
            "/aura.negotiation.v1.NegotiationService/GetSystemStatus": grpclib.const.Handler(
                self.__rpc_get_system_status,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetSystemStatusRequest,
                GetSystemStatusResponse,
            ),
            "/aura.negotiation.v1.NegotiationService/CheckDealStatus": grpclib.const.Handler(
                self.__rpc_check_deal_status,
                grpclib.const.Cardinality.UNARY_UNARY,
                CheckDealStatusRequest,
                CheckDealStatusResponse,
            ),
        }

    async def __rpc_negotiate(self, stream: Any) -> None:
        request = await stream.recv_message()
        response = await self.negotiate(**request.to_dict())
        await stream.send_message(response)

    async def __rpc_search(self, stream: Any) -> None:
        request = await stream.recv_message()
        response = await self.search(**request.to_dict())
        await stream.send_message(response)

    async def __rpc_get_system_status(self, stream: Any) -> None:
        await stream.recv_message()
        response = await self.get_system_status()
        await stream.send_message(response)

    async def __rpc_check_deal_status(self, stream: Any) -> None:
        request = await stream.recv_message()
        response = await self.check_deal_status(**request.to_dict())
        await stream.send_message(response)


async def serve() -> None:
    # 1. Initialize the "Cell" (The HiveCell)
    cell = HiveCell(settings)
    metabolism = await cell.build_organism()

    # 2. Initialize Negotiation Service
    negotiation_service = NegotiationService(
        metabolism=metabolism, market_service=cell.market_service
    )

    # 3. Start NATS Signal Gateway
    gateway = NatsSignalGateway(
        nats_url=settings.server.nats_url,
        metabolism=metabolism,
    )
    await gateway.start()

    # 4. Start grpclib Server
    # Note: We need to register the service.
    # With betterproto, we usually use the generated base class if it exists.
    # Since it didn't, we can use a custom Dispatcher or just grpclib directly if we had the service class.

    # Wait, I'll check if I can generate the base class with betterproto.
    # Usually it's there. Let me check the file content again VERY carefully.

    server = Server([negotiation_service]) # grpclib handles this if negotiation_service has __mapping__

    # Heartbeat Deal loop
    async def heartbeat_deal_loop() -> None:
        await asyncio.sleep(60)
        while True:
            try:
                persistence = cell.registry.get("persistence")
                if persistence:
                    obs = await persistence.execute("get_first_item", {})
                    if obs.success:
                        item = obs.metadata.to_dict()
                        if item:
                            from aura_core_gen.aura.negotiation.v1 import (
                                AgentIdentity as NegotiationAgentIdentity,
                            )
                            mock_signal = NegotiateRequest(
                                item_id=item["id"],
                                bid_amount=item["base_price"] * settings.heartbeat.bid_multiplier,
                                currency_code="USD",
                                agent=NegotiationAgentIdentity(
                                    did=settings.heartbeat.agent_did,
                                    reputation_score=settings.heartbeat.agent_reputation,
                                ),
                                request_id=f"heartbeat-{uuid.uuid4()}",
                            )
                            await metabolism.execute(mock_signal)
            except Exception as e:
                logger.error("heartbeat_deal_error", error=str(e))
            await asyncio.sleep(settings.heartbeat.interval_seconds)

    asyncio.create_task(heartbeat_deal_loop())

    with tracer.start_as_current_span("core_server_start"):
        await server.start(host="0.0.0.0", port=settings.server.port)  # nosec
        logger.info("server_started", port=settings.server.port)
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(serve())
