import asyncio
import uuid
from concurrent import futures
from typing import Any, Protocol

import grpc
import grpc.aio
import nats
from grpc_health.v1 import health_pb2, health_pb2_grpc
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_client import start_http_server
from sqlalchemy import text

from src.config import settings
from src.config.llm import get_raw_key
from src.db import InventoryItem, SessionLocal, engine
from src.embeddings import generate_embedding
from src.hive.aggregator import HiveAggregator
from src.hive.connector import HiveConnector
from src.hive.generator import HiveGenerator
from src.hive.membrane import HiveMembrane
from src.hive.metabolism import MetabolicLoop
from src.hive.transformer import HiveTransformer
from src.logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from src.proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from src.telemetry import init_telemetry

# Configure structured logging on startup
configure_logging(log_level=settings.server.log_level)
logger = get_logger("core-service")

# Initialize OpenTelemetry tracing
service_name = settings.server.otel_service_name
tracer = init_telemetry(service_name, str(settings.server.otel_exporter_otlp_endpoint))
logger.info(
    "telemetry_initialized",
    service_name=service_name,
    endpoint=str(settings.server.otel_exporter_otlp_endpoint),
)

# Instrument gRPC server for distributed tracing
GrpcInstrumentorServer().instrument()

# Instrument SQLAlchemy for database query tracing
SQLAlchemyInstrumentor().instrument(engine=engine)

# Instrument LangChain for LLM call tracing
LangchainInstrumentor().instrument()

# gRPC metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


def extract_request_id(context: Any) -> str | None:
    """Extract request_id from gRPC metadata."""
    metadata = dict(context.invocation_metadata())
    return metadata.get(REQUEST_ID_METADATA_KEY)


class PricingStrategy(Protocol):
    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None
    ) -> negotiation_pb2.NegotiateResponse: ...


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
            return observation.data  # type: ignore

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

    def Search(self, request: Any, context: Any) -> negotiation_pb2.SearchResponse:
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
        self, request: negotiation_pb2.GetSystemStatusRequest, context: Any
    ) -> negotiation_pb2.GetSystemStatusResponse:
        """Return infrastructure metrics from Prometheus."""
        if not self.metabolism:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Metabolism is still initializing")
            return negotiation_pb2.GetSystemStatusResponse(status="initializing")

        try:
            metrics = await self.metabolism.aggregator.get_system_metrics()
            return negotiation_pb2.GetSystemStatusResponse(
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
            return negotiation_pb2.GetSystemStatusResponse(status="error")

    async def CheckDealStatus(
        self, request: negotiation_pb2.CheckDealStatusRequest, context: Any
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """Check crypto payment status and reveal secret if paid."""
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

            # Check payment status
            session = SessionLocal()
            try:
                response = await self.market_service.check_status(
                    db=session, deal_id=request.deal_id
                )

                logger.info(
                    "check_deal_status_completed",
                    deal_id=request.deal_id,
                    status=response.status,
                )
                return response  # type: ignore
            finally:
                session.close()

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


def create_strategy() -> PricingStrategy:
    """Create pricing strategy based on LLM_MODEL configuration.

    Strategies:
    - "rule": RuleBasedStrategy (no LLM required)
    - "dspy": DSPyStrategy (self-optimizing negotiation engine)
    - Any litellm model: LiteLLMStrategy (e.g., "openai/gpt-4o", "mistral/mistral-large-latest")

    Returns:
        Strategy instance implementing PricingStrategy protocol
    """
    if settings.llm.model == "rule":
        logger.info("strategy_selected", type="RuleBasedStrategy", llm_required=False)
        from src.llm_strategy import RuleBasedStrategy

        return RuleBasedStrategy()
    elif settings.llm.model == "dspy":
        logger.info("strategy_selected", type="DSPyStrategy", model="self-optimizing")
        from src.llm.dspy_strategy import DSPyStrategy

        return DSPyStrategy()
    else:
        logger.info(
            "strategy_selected", type="LiteLLMStrategy", model=settings.llm.model
        )
        from src.llm.strategy import LiteLLMStrategy

        # Select appropriate API key based on model provider
        api_key = None
        if settings.llm.model.startswith("openai/"):
            api_key = get_raw_key(settings.llm.openai_api_key)
        elif settings.llm.model.startswith("mistral/"):
            api_key = get_raw_key(settings.llm.api_key)

        return LiteLLMStrategy(
            model=settings.llm.model,
            temperature=settings.llm.temperature,
            api_key=api_key,
        )


def create_crypto_provider() -> Any:
    """Create crypto payment provider if enabled.

    Returns:
        CryptoProvider instance or None if crypto disabled
    """
    if not settings.crypto.enabled:
        logger.info("crypto_disabled", feature="crypto_payments")
        return None

    if settings.crypto.provider == "solana":
        logger.info(
            "crypto_provider_initialized",
            provider="solana",
            network=settings.crypto.solana_network,
            currency=settings.crypto.currency,
        )
        from src.crypto.solana_provider import SolanaProvider

        return SolanaProvider(
            private_key_base58=get_raw_key(settings.crypto.solana_private_key),
            rpc_url=str(settings.crypto.solana_rpc_url),
            network=settings.crypto.solana_network,
            usdc_mint=settings.crypto.solana_usdc_mint,
        )
    else:
        logger.warning("unknown_crypto_provider", provider=settings.crypto.provider)
        return None


async def serve() -> None:
    from grpc_health.v1 import health

    # 1. Initialize gRPC Server early
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.server.grpc_max_workers)
    )

    # 2. Register Health Service immediately
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # 3. Register Negotiation Service with placeholder components
    # This allows the server to start even while heavy LLM components are loading.
    negotiation_service = NegotiationService(metabolism=None, market_service=None)
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        negotiation_service, server
    )

    # 4. Bind and Start the server
    server.add_insecure_port(f"[::]:{settings.server.port}")
    await server.start()
    logger.info(
        "server_started_early",
        port=settings.server.port,
        status="INITIALIZING",
        note="Health checks active, main logic loading...",
    )

    # 5. Verify Database Connection (Shallow check for initial Serving status)
    try:
        # Use a new session for the health check
        with SessionLocal() as session:
            await asyncio.to_thread(session.execute, text("SELECT 1"))
        health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
        logger.info("db_verified_health_serving")
    except Exception as e:
        logger.error("db_verification_failed", error=str(e))
        # Keep status as UNKNOWN/NOT_SERVING if DB is not reachable

    # 6. Start Prometheus metrics server
    try:
        start_http_server(9091)
        logger.info("metrics_server_started", port=9091)
    except Exception as e:
        logger.error("metrics_server_failed", error=str(e))

    # 7. Initialize Heavy Components (NATS, AI Models, Crypto)
    nc = None
    try:
        nc = await nats.connect(settings.server.nats_url)
        logger.info("nats_connected", url=settings.server.nats_url)
    except Exception as e:
        logger.warning(
            "nats_connection_failed", url=settings.server.nats_url, error=str(e)
        )

    crypto_provider = create_crypto_provider()
    market_service = None
    if crypto_provider:
        from src.crypto.encryption import SecretEncryption
        from src.services.market import MarketService

        encryption = SecretEncryption(
            get_raw_key(settings.crypto.secret_encryption_key)
        )
        market_service = MarketService(crypto_provider, encryption)
        logger.info("market_service_initialized")

    # Initialize Hive components (Aggregator, Transformer/LLM, etc.)
    aggregator = HiveAggregator()
    transformer = HiveTransformer()  # Heavy: Loads DSPy/LLM
    connector = HiveConnector(market_service=market_service)
    generator = HiveGenerator(nats_client=nc)
    membrane = HiveMembrane()

    metabolism = MetabolicLoop(
        aggregator=aggregator,
        transformer=transformer,
        connector=connector,
        generator=generator,
        membrane=membrane,
    )

    # 8. Wire fully initialized components into the NegotiationService
    negotiation_service.metabolism = metabolism
    negotiation_service.market_service = market_service

    logger.info(
        "initialization_complete",
        services=["NegotiationService", "Health"],
        crypto_enabled=settings.crypto.enabled,
        metabolism="ATCG",
    )

    try:
        await server.wait_for_termination()
    finally:
        if nc:
            await nc.close()
            logger.info("nats_connection_closed")
        if crypto_provider:
            await crypto_provider.close()
            logger.info("crypto_provider_closed")


if __name__ == "__main__":
    asyncio.run(serve())
