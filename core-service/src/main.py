import time
from concurrent import futures
from typing import Protocol

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
from logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from telemetry import init_telemetry

from config import get_settings
from db import InventoryItem, SessionLocal, engine
from embeddings import generate_embedding
from monitor import get_hive_metrics
from proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

# Configure structured logging on startup
configure_logging()
logger = get_logger("core-service")

settings = get_settings()

# Initialize OpenTelemetry tracing
service_name = settings.otel_service_name
tracer = init_telemetry(service_name, settings.otel_exporter_otlp_endpoint)
logger.info(
    "telemetry_initialized",
    service_name=service_name,
    endpoint=settings.otel_exporter_otlp_endpoint,
)

# Instrument gRPC server for distributed tracing
GrpcInstrumentorServer().instrument()

# Instrument SQLAlchemy for database query tracing
SQLAlchemyInstrumentor().instrument(engine=engine)

# Instrument LangChain for LLM call tracing
LangchainInstrumentor().instrument()

# gRPC metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


def extract_request_id(context) -> str | None:
    """Extract request_id from gRPC metadata."""
    metadata = dict(context.invocation_metadata())
    return metadata.get(REQUEST_ID_METADATA_KEY)


class PricingStrategy(Protocol):
    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None
    ) -> negotiation_pb2.NegotiateResponse: ...


class NegotiationService(negotiation_pb2_grpc.NegotiationServiceServicer):
    def __init__(self, strategy: PricingStrategy):
        self.strategy = strategy

    def Negotiate(self, request, context):
        request_id = extract_request_id(context) or request.request_id
        bind_request_id(request_id)

        try:
            logger.info(
                "negotiate_request_received",
                item_id=request.item_id,
                bid_amount=request.bid_amount,
                agent_did=request.agent.did,
            )

            if request.bid_amount <= 0:
                logger.error(
                    "invalid_bid_amount",
                    bid_amount=request.bid_amount,
                    error="Bid amount must be positive",
                )
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Bid amount must be positive")
                return negotiation_pb2.NegotiateResponse()

            response = self.strategy.evaluate(
                item_id=request.item_id,
                bid=request.bid_amount,
                reputation=request.agent.reputation_score,
                request_id=request_id,
            )

            response.session_token = "sess_" + request.request_id
            response.valid_until_timestamp = int(time.time() + 600)

            logger.info(
                "negotiate_response_sent",
                session_token=response.session_token,
                result_type=response.WhichOneof("result"),
            )

            return response
        finally:
            clear_request_context()

    def Search(self, request, context):
        """Semantic search implementation."""
        request_id = extract_request_id(context)
        if request_id:
            bind_request_id(request_id)

        try:
            logger.info("search_started", query=request.query, limit=request.limit)

            # Generate query vector
            query_vector = generate_embedding(request.query)
            if not query_vector:
                logger.error("embedding_generation_failed", query=request.query)
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Failed to generate embeddings")
                return negotiation_pb2.SearchResponse()

            # Vector search in database
            session = SessionLocal()
            try:
                results = (
                    session.query(
                        InventoryItem,
                        InventoryItem.embedding.cosine_distance(query_vector).label(
                            "distance"
                        ),
                    )
                    .order_by(InventoryItem.embedding.cosine_distance(query_vector))
                    .limit(request.limit or 5)
                    .all()
                )

                response_items = []
                for item, distance in results:
                    similarity = 1 - distance

                    if request.min_similarity and similarity < request.min_similarity:
                        continue

                    response_items.append(
                        negotiation_pb2.SearchResultItem(
                            item_id=item.id,
                            name=item.name,
                            base_price=item.base_price,
                            similarity_score=similarity,
                            description_snippet=str(item.meta),
                        )
                    )

                logger.info("search_completed", result_count=len(response_items))
                return negotiation_pb2.SearchResponse(results=response_items)

            except Exception as e:
                logger.error("db_error", error=str(e))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return negotiation_pb2.SearchResponse()

            finally:
                session.close()
        finally:
            if request_id:
                clear_request_context()

    async def GetSystemStatus(
        self, request: negotiation_pb2.SystemStatusRequest, context
    ) -> negotiation_pb2.SystemStatusResponse:
        """Return infrastructure metrics from Prometheus."""
        try:
            metrics = await get_hive_metrics()
            return negotiation_pb2.SystemStatusResponse(
                status=metrics["status"],
                cpu_usage_percent=metrics.get("cpu_usage_percent", 0.0),
                memory_usage_mb=metrics.get("memory_usage_mb", 0.0),
                timestamp=metrics.get("timestamp", ""),
                cached=metrics.get("cached", False),
            )
        except Exception as e:
            logger.error("system_status_error", error=str(e), exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve system metrics")
            return negotiation_pb2.SystemStatusResponse(status="error")


class HealthServicer(health_pb2_grpc.HealthServicer):
    """gRPC Health Checking Protocol implementation for Core Service.

    Implements the standard grpc.health.v1.Health service to allow clients
    (including load balancers and orchestrators) to verify service health.

    The health check verifies database connectivity by executing a simple
    query. This ensures the service can handle actual requests.
    """

    def Check(self, request, context):
        """Performs synchronous health check.

        Verifies that the Core Service can connect to and query the database.
        Returns SERVING if healthy, NOT_SERVING if database is unreachable.

        Args:
            request: HealthCheckRequest (service name, typically empty)
            context: gRPC context

        Returns:
            HealthCheckResponse with status SERVING or NOT_SERVING
        """
        try:
            session = SessionLocal()
            try:
                session.execute(text("SELECT 1"))
                logger.debug("health_check_passed", component="database")
                return health_pb2.HealthCheckResponse(
                    status=health_pb2.HealthCheckResponse.SERVING
                )
            finally:
                session.close()
        except SQLAlchemyError as e:
            logger.error("health_check_failed", error=str(e), exc_info=True)
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.NOT_SERVING
            )

    def Watch(self, request, context):
        """Health status streaming (not implemented).

        The Watch method allows clients to stream health status changes.
        This is not currently implemented as we use polling-based checks.

        Args:
            request: HealthCheckRequest
            context: gRPC context

        Returns:
            HealthCheckResponse (never called, raises UNIMPLEMENTED)
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Health status streaming not implemented")
        return health_pb2.HealthCheckResponse()


def create_strategy():
    """Create pricing strategy based on LLM_MODEL configuration.

    Strategies:
    - "rule": RuleBasedStrategy (no LLM required)
    - Any litellm model: LiteLLMStrategy (e.g., "openai/gpt-4o", "mistral/mistral-large-latest")

    Returns:
        Strategy instance implementing PricingStrategy protocol
    """
    settings = get_settings()

    if settings.llm_model == "rule":
        logger.info("strategy_selected", type="RuleBasedStrategy", llm_required=False)
        from llm_strategy import RuleBasedStrategy

        return RuleBasedStrategy()
    else:
        logger.info("strategy_selected", type="LiteLLMStrategy", model=settings.llm_model)
        from llm.strategy import LiteLLMStrategy

        return LiteLLMStrategy(model=settings.llm_model)


def serve():
    strategy = create_strategy()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers)
    )

    # Register negotiation service
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        NegotiationService(strategy), server
    )

    # Register health service
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    logger.info(
        "server_started",
        port=settings.grpc_port,
        database="postgres",
        services=["NegotiationService", "Health"],
    )
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
