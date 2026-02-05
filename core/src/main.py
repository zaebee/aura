import asyncio
import uuid
from concurrent import futures
from typing import Any

import grpc
import grpc.aio
from aura_core import SkillRegistry
from grpc_health.v1 import health_pb2, health_pb2_grpc
from hive.aggregator import HiveAggregator
from hive.connector import HiveConnector
from hive.generator import HiveGenerator
from hive.membrane import HiveMembrane
from hive.metabolism import MetabolicLoop
from hive.metabolism.logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from hive.proteins.telemetry.enzymes.prometheus import init_telemetry
from hive.proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from hive.transformer import AuraTransformer
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from prometheus_client import start_http_server

from config import settings

# Configure structured logging on startup
configure_logging(log_level=settings.server.log_level)
logger = get_logger("core")

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


# Instrument LangChain for LLM call tracing
LangchainInstrumentor().instrument()

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
            if not embed_obs.success:
                logger.error(
                    "embedding_generation_failed",
                    query=request.query,
                    error=embed_obs.error,
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Failed to generate embeddings")
                return negotiation_pb2.SearchResponse()

            query_vector = embed_obs.data

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
            for item in obs.data:
                response_items.append(
                    negotiation_pb2.SearchResultItem(
                        item_id=item["id"],
                        name=item["name"],
                        base_price=item["base_price"],
                        similarity_score=item["similarity_score"],
                        description_snippet=str(item["meta"]),
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
                status=vitals.status,
                cpu_usage_percent=vitals.cpu_usage_percent,
                memory_usage_mb=vitals.memory_usage_mb,
                timestamp=vitals.timestamp,
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
    )

    # 5. Start Prometheus metrics server
    try:
        start_http_server(9091)
        logger.info("metrics_server_started", port=9091)
    except Exception as e:
        logger.error("metrics_server_failed", error=str(e))

    # 6. Initialize Skills (Proteins)
    registry = SkillRegistry()

    import dspy
    from aura_core import get_raw_key
    from hive.proteins.guard import GuardSkill
    from hive.proteins.guard.enzymes.guard_logic import OutputGuard
    from hive.proteins.persistence import PersistenceSkill
    from hive.proteins.pulse import PulseSkill
    from hive.proteins.pulse.enzymes.pulse_broker import NatsProvider
    from hive.proteins.reasoning import ReasoningSkill
    from hive.proteins.reasoning.enzymes.reasoning_engine import get_embedding_model
    from hive.proteins.telemetry import TelemetrySkill
    from hive.proteins.transaction import TransactionSkill
    from hive.proteins.transaction.enzymes.solana import (
        PriceConverter,
        SecretEncryption,
        SolanaProvider,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # --- Provider Factories (Trinity Pattern) ---

    # Persistence Provider
    engine = create_engine(str(settings.database.url))
    SessionLocal = sessionmaker(bind=engine)

    # Pulse Provider
    nats_provider = NatsProvider(settings.server.nats_url)

    # Transaction Provider (if enabled)
    transaction_bundle = {}
    if settings.crypto.enabled:
        transaction_bundle = {
            "provider": SolanaProvider(
                private_key_base58=get_raw_key(settings.crypto.solana_private_key),
                rpc_url=str(settings.crypto.solana_rpc_url),
                usdc_mint=settings.crypto.solana_usdc_mint,
            ),
            "encryption": SecretEncryption(
                get_raw_key(settings.crypto.secret_encryption_key)
            ),
            "converter": PriceConverter(),
        }

    # Reasoning Provider
    lm = None
    embedder = None
    if settings.llm.model.lower() != "rule":
        lm = dspy.LM(settings.llm.model)
        embedder = get_embedding_model(get_raw_key(settings.llm.api_key))
    reasoning_provider = {"lm": lm, "embedder": embedder}

    # Guard Provider
    guard_provider = OutputGuard(safety_settings=settings.safety)

    # --- Skill Instantiation & Binding ---

    persistence_protein = PersistenceSkill()
    persistence_protein.bind(settings.database, (SessionLocal, engine))

    pulse_protein = PulseSkill()
    pulse_protein.bind(settings.server, nats_provider)

    reasoning_protein = ReasoningSkill()
    reasoning_protein.bind(settings.llm, reasoning_provider)

    telemetry_protein = TelemetrySkill()
    telemetry_protein.bind(settings.server, None)

    guard_protein = GuardSkill()
    guard_protein.bind(settings.safety, guard_provider)

    transaction_protein = None
    if settings.crypto.enabled:
        transaction_protein = TransactionSkill()
        transaction_protein.bind(settings.crypto, transaction_bundle)

    # Register in registry
    registry.register("persistence", persistence_protein)
    if transaction_protein:
        registry.register("transaction", transaction_protein)
    registry.register("reasoning", reasoning_protein)
    registry.register("telemetry", telemetry_protein)
    registry.register("pulse", pulse_protein)
    registry.register("guard", guard_protein)

    # 7. Initialize and Verify Skills
    await persistence_protein.execute("init_db", {})
    if await persistence_protein.initialize():
        health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
        logger.info("db_verified_health_serving")
    else:
        logger.error("db_verification_failed")

    await pulse_protein.initialize()
    await reasoning_protein.initialize()
    await telemetry_protein.initialize()
    await guard_protein.initialize()
    if transaction_protein:
        await transaction_protein.initialize()

    # 8. Initialize Nucleotides
    aggregator = HiveAggregator(registry=registry, settings=settings)
    transformer = AuraTransformer(registry=registry, settings=settings)

    market_service = None
    if transaction_protein:
        from hive.services.market import MarketService

        market_service = MarketService(
            persistence=persistence_protein, transaction=transaction_protein
        )
        logger.info("market_service_initialized")

    connector = HiveConnector(
        registry=registry, market_service=market_service, settings=settings
    )
    generator = HiveGenerator(registry=registry, settings=settings)
    membrane = HiveMembrane(registry=registry)

    metabolism = MetabolicLoop(
        aggregator=aggregator,
        transformer=transformer,
        connector=connector,
        generator=generator,
        membrane=membrane,
        registry=registry,
    )

    # 9. Wire fully initialized components into the NegotiationService
    negotiation_service.metabolism = metabolism
    negotiation_service.market_service = market_service

    # 10. Start Heartbeat Deal (Honey Stimulus)
    async def heartbeat_deal_loop() -> None:
        """Trigger a mock successful negotiation periodically."""
        await asyncio.sleep(60)
        while True:
            try:
                logger.info("triggering_heartbeat_deal")
                obs = await persistence_protein.execute("get_first_item", {})

                if obs.success and obs.data:
                    item = obs.data
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
                    await metabolism.execute(mock_signal, is_heartbeat=True)
                    logger.info("heartbeat_deal_successful")
                else:
                    logger.warning("heartbeat_deal_failed_no_items")
            except Exception as e:
                logger.error("heartbeat_deal_error", error=str(e))

            await asyncio.sleep(settings.heartbeat.interval_seconds)

    asyncio.create_task(heartbeat_deal_loop())

    logger.info(
        "initialization_complete",
        services=["NegotiationService", "Health"],
        crypto_enabled=settings.crypto.enabled,
        metabolism="ATCG",
    )

    try:
        await server.wait_for_termination()
    finally:
        await registry.close()
        logger.info("all_skills_closed")


if __name__ == "__main__":
    asyncio.run(serve())
