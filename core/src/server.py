import asyncio
import uuid
from typing import Any

import grpc
import grpc.aio
from aura_core import MetabolicLoop
from hive.metabolism.logging_config import (
    bind_request_id,
    clear_request_context,
    get_logger,
)
from hive.proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from opentelemetry import trace

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
        """
        Main metabolic loop for negotiation:
        Signal -> A -> T -> Membrane -> C -> G
        """
        if not self.metabolism:
            logger.warning("negotiate_called_before_initialization")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Metabolism is still initializing")
            return negotiation_pb2.NegotiateResponse()

        request_id = str(
            extract_request_id(context)
            or getattr(request, "request_id", str(uuid.uuid4()))
        )
        bind_request_id(request_id)

        try:
            observation = await self.metabolism.execute(request)
            if observation.negotiation:
                from google.protobuf.json_format import ParseDict
                import betterproto
                obs_dict = observation.negotiation.to_dict(casing=betterproto.Casing.SNAKE)
                resp = negotiation_pb2.NegotiateResponse()
                ParseDict(obs_dict, resp, ignore_unknown_fields=True)
                return resp
            return negotiation_pb2.NegotiateResponse()

        except ValueError as e:
            logger.warning("invalid_argument", error=str(e))
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return negotiation_pb2.NegotiateResponse()
        except Exception as e:
            logger.error("metabolic_failure", error=str(e), exc_info=True)
            # Record exception in the OTel span
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

            # Generate query vector via Reasoning Protein
            aggregator = getattr(self.metabolism, "aggregator", None)
            registry = getattr(aggregator, "registry", None) if aggregator else None
            if not registry:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Skill Registry not available")
                return negotiation_pb2.SearchResponse()

            reasoning = registry.get("reasoning")
            if not reasoning:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Reasoning protein not available")
                return negotiation_pb2.SearchResponse()

            embed_obs = await reasoning.execute(
                "generate_embedding", {"text": request.query}
            )
            if not embed_obs.success or not embed_obs.float_list:
                logger.error(
                    "embedding_generation_failed",
                    query=request.query,
                    error=embed_obs.error,
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Failed to generate embeddings")
                return negotiation_pb2.SearchResponse()

            query_vector = embed_obs.float_list.values

            # Vector search via Persistence Protein
            persistence = registry.get("persistence")
            if not persistence:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Persistence protein not available")
                return negotiation_pb2.SearchResponse()

            obs = await persistence.execute(
                "vector_search",
                {
                    "query_vector": query_vector,
                    "limit": request.limit or 5,
                    "min_similarity": request.min_similarity,
                },
            )

            if not obs.success:
                logger.error("search_failed", error=obs.error)
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(obs.error)
                return negotiation_pb2.SearchResponse()

            response_items = []
            if obs.item_list:
                for item in obs.item_list.items:
                    response_items.append(
                        negotiation_pb2.SearchResultItem(
                            item_id=item.id,
                            name=item.name,
                            base_price=item.base_price,
                            # similarity_score would need to come from somewhere else now
                            description_snippet=str(item.meta),
                        )
                    )

            logger.info("search_completed", result_count=len(response_items))
            return negotiation_pb2.SearchResponse(results=response_items)

        except Exception as e:
            logger.error("search_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return negotiation_pb2.SearchResponse()
        finally:
            if request_id:
                clear_request_context()

    async def GetSystemStatus(
        self, request: negotiation_pb2.GetSystemStatusRequest, context: Any
    ) -> negotiation_pb2.GetSystemStatusResponse:
        """Return infrastructure metrics from Prometheus."""
        if not self.metabolism:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Metabolism is still initializing")
            return negotiation_pb2.GetSystemStatusResponse(status="initializing")

        try:
            # Use standardized get_vitals() from the Aggregator protocol
            vitals = await self.metabolism.aggregator.get_vitals()
            return negotiation_pb2.GetSystemStatusResponse(
                status=vitals.status.name if hasattr(vitals.status, "name") else str(vitals.status),
                cpu_usage_percent=vitals.cpu_usage_percent,
                memory_usage_mb=vitals.memory_usage_mb,
                timestamp=vitals.timestamp.isoformat() if hasattr(vitals.timestamp, "isoformat") else str(vitals.timestamp),
                cached=vitals.cached,
            )
        except Exception as e:
            logger.error("system_status_error", error=str(e), exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve system metrics")
            return negotiation_pb2.GetSystemStatusResponse(status="error")

    async def CheckDealStatus(
        self, request: negotiation_pb2.CheckDealStatusRequest, context: Any
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """Check crypto payment status and reveal secret if paid."""
        from config import settings
        request_id = extract_request_id(context)
        if request_id:
            bind_request_id(request_id)

        try:
            # Feature toggle check
            if not settings.crypto.enabled or not self.market_service:
                logger.warning("crypto_disabled", deal_id=request.deal_id)
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Crypto payments not enabled")
                return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

            # Validate UUID format
            try:
                uuid.UUID(request.deal_id)
            except ValueError:
                logger.warning("invalid_deal_id", deal_id=request.deal_id)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Invalid deal_id format")
                return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

            logger.info("check_deal_status_started", deal_id=request.deal_id)

            # Check payment status via MarketService
            response = await self.market_service.check_status(deal_id=request.deal_id)

            logger.info(
                "check_deal_status_completed",
                deal_id=request.deal_id,
                status=response.status,
            )
            return response  # type: ignore

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
