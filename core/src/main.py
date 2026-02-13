import asyncio
import uuid
from concurrent import futures
from typing import Any, cast

import betterproto
import grpc
import grpc.aio
from aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
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

# 1. Configure structured logging
configure_logging(log_level=settings.server.log_level)
logger = get_logger("core")

# gRPC metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


def extract_request_id(context: Any) -> str | None:
    """Extract request_id from gRPC metadata."""
    metadata = dict(context.invocation_metadata())
    return metadata.get(REQUEST_ID_METADATA_KEY)


class NegotiationService(negotiation_pb2_grpc.NegotiationServiceServicer):
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

    async def Negotiate(
        self, request: Any, context: Any
    ) -> negotiation_pb2.NegotiateResponse:
        """Main metabolic loop for negotiation."""
        if not self.metabolism:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Metabolism is still initializing")
            return negotiation_pb2.NegotiateResponse()

        request_id = str(
            extract_request_id(context)
            or getattr(request, "request_id", str(uuid.uuid4()))
        )
        bind_request_id(request_id)

        try:
            # Execute metabolic cycle
            observation = await self.metabolism.execute(request)

            # Map new Observation proto back to legacy NegotiateResponse for boundary compatibility
            response = negotiation_pb2.NegotiateResponse()
            response.session_token = "sess_" + request_id

            if observation.negotiation:
                neg = observation.negotiation
                response.valid_until_timestamp = neg.valid_until_timestamp

                res_name, res_val = betterproto.which_one_of(neg, "result")
                if res_name == "accepted" and res_val:
                    response.accepted.final_price = res_val.final_price
                    if hasattr(res_val, "reservation_code") and res_val.reservation_code:
                        response.accepted.reservation_code = res_val.reservation_code
                    if hasattr(res_val, "crypto_payment") and res_val.crypto_payment:
                         # Handled via mapping if available
                         pass
                elif res_name == "countered" and res_val:
                    response.countered.proposed_price = res_val.proposed_price
                    response.countered.human_message = res_val.human_message
                elif res_name == "rejected" and res_val:
                    response.rejected.reason_code = res_val.reason_code
                    # If it was UI_REQUIRED, we might want to map it to ui_required in legacy response
                    if res_val.reason_code == "UI_REQUIRED":
                         # Legacy response might not have ui_required, let's check
                         pass

            return response

        except ValueError as e:
            logger.warning("invalid_argument", error=str(e))
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return negotiation_pb2.NegotiateResponse()
        except Exception as e:
            logger.error("metabolic_failure", error=str(e), exc_info=True)
            current_span = trace.get_current_span()
            if current_span:
                current_span.record_exception(e)
                current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Metabolic failure: {e}")
            return negotiation_pb2.NegotiateResponse()
        finally:
            clear_request_context()

    async def Search(
        self, request: Any, context: Any
    ) -> negotiation_pb2.SearchResponse:
        """Semantic search implementation."""
        request_id = extract_request_id(context)
        if request_id:
            bind_request_id(request_id)

        try:
            logger.info("search_started", query=request.query, limit=request.limit)

            registry = getattr(self.metabolism, "registry", None)
            if not registry:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Skill Registry not available")
                return negotiation_pb2.SearchResponse()

            reasoning = registry.get("reasoning")
            persistence = registry.get("persistence")

            if not reasoning or not persistence:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Required proteins not available")
                return negotiation_pb2.SearchResponse()

            embed_obs = await reasoning.execute(
                "generate_embedding", {"text": request.query}
            )
            if not embed_obs.success:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Failed to generate embedding: {embed_obs.error}")
                return negotiation_pb2.SearchResponse()

            # embed_obs.data might be in metadata
            query_vector = getattr(embed_obs, "metadata", {}).get("embedding") or []

            obs = await persistence.execute(
                "vector_search",
                {
                    "query_vector": query_vector,
                    "limit": request.limit or 5,
                    "min_similarity": request.min_similarity,
                },
            )

            if not obs.success:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Search failed: {obs.error}")
                return negotiation_pb2.SearchResponse()

            # obs.data doesn't exist, use metadata
            items = getattr(obs, "metadata", {}).get("results", [])
            response_items = [
                negotiation_pb2.SearchResultItem(
                    item_id=item["id"],
                    name=item["name"],
                    base_price=item["base_price"],
                    similarity_score=item["similarity_score"],
                    description_snippet=str(item["meta"]),
                )
                for item in items
            ]

            return negotiation_pb2.SearchResponse(results=response_items)

        except Exception as e:
            logger.error("search_error", error=str(e), exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return negotiation_pb2.SearchResponse()
        finally:
            if request_id:
                clear_request_context()

    async def GetSystemStatus(
        self, request: negotiation_pb2.GetSystemStatusRequest, context: Any
    ) -> negotiation_pb2.GetSystemStatusResponse:
        """Return infrastructure metrics."""
        if not self.metabolism:
            return negotiation_pb2.GetSystemStatusResponse(status="initializing")

        try:
            vitals = await self.metabolism.aggregator.get_vitals()
            return negotiation_pb2.GetSystemStatusResponse(
                status=str(vitals.status),
                cpu_usage_percent=float(vitals.cpu_usage_percent),
                memory_usage_mb=float(vitals.memory_usage_mb),
                timestamp=str(vitals.timestamp),
            )
        except Exception as e:
            logger.error("system_status_error", error=str(e), exc_info=True)
            return negotiation_pb2.GetSystemStatusResponse(status="error")

    async def CheckDealStatus(
        self, request: negotiation_pb2.CheckDealStatusRequest, context: Any
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """Check crypto payment status."""
        request_id = extract_request_id(context)
        if request_id:
            bind_request_id(request_id)

        try:
            if not settings.crypto.enabled or not self.market_service:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Crypto payments not enabled")
                return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

            # Validate UUID format
            try:
                uuid.UUID(request.deal_id)
            except ValueError:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Invalid deal_id format")
                return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

            response = cast(
                negotiation_pb2.CheckDealStatusResponse,
                await self.market_service.check_status(deal_id=request.deal_id),
            )
            return response

        except Exception as e:
            logger.error(
                "check_deal_status_error",
                deal_id=request.deal_id,
                error=str(e),
                exc_info=True,
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Payment verification failed")
            return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")
        finally:
            if request_id:
                clear_request_context()


async def serve() -> None:
    from grpc_health.v1 import health

    # 1. Initialize gRPC Server
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.server.grpc_max_workers)
    )

    # 2. Register Health Service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # 3. Register Negotiation Service
    negotiation_service = NegotiationService()
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        negotiation_service, server
    )

    # 4. Start the server early
    server.add_insecure_port(f"[::]:{settings.server.port}")
    await server.start()
    logger.info("server_started_early", port=settings.server.port)

    # 5. Initialize the "Cell" (The HiveCell)
    cell = HiveCell(settings)
    metabolism = await cell.build_organism()

    # 6. Wire fully initialized components
    negotiation_service.metabolism = metabolism
    negotiation_service.market_service = cell.market_service

    # 7. Start NATS Signal Gateway (receives signals from synapses via NATS)
    gateway = NatsSignalGateway(
        nats_url=settings.server.nats_url,
        metabolism=metabolism,
    )
    gateway_started = await gateway.start()
    if gateway_started:
        logger.info("nats_signal_gateway_started")
    else:
        logger.warning("nats_signal_gateway_failed_to_start")

    # Set health to SERVING once DB/Metabolism is up
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    # 8. Start Heartbeat Deal (Honey Stimulus)
    async def heartbeat_deal_loop() -> None:
        await asyncio.sleep(60)
        while True:
            try:
                persistence = cell.registry.get("persistence")
                if not persistence:
                    continue
                obs = await persistence.execute("get_first_item", {})
                if obs.success:
                    item = getattr(obs, "metadata", {}).get("item", {})
                    if item:
                        mock_signal = negotiation_pb2.NegotiateRequest(
                            item_id=item["id"],
                            bid_amount=item["base_price"]
                            * settings.heartbeat.bid_multiplier,
                            currency_code="USD",
                            agent=negotiation_pb2.AgentIdentity(
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

    logger.info("initialization_complete", status="SERVING")

    try:
        await server.wait_for_termination()
    finally:
        await gateway.stop()
        await cell.registry.close()


if __name__ == "__main__":
    asyncio.run(serve())
