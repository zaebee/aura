import asyncio
import uuid
from concurrent import futures
from typing import Any

import grpc
import grpc.aio
import nats
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
from hive.metabolism.telemetry import init_telemetry
from hive.proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from hive.transformer import AuraTransformer
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from prometheus_client import start_http_server

from config import settings
from config.llm import get_raw_key

# Configure structured logging on startup
configure_logging(log_level=settings.server.log_level)
logger = get_logger("core")

# Initialize OpenTelemetry tracing
service_name = settings.server.otel_service_name
tracer = init_telemetry(service_name, str(settings.server.otel_exporter_otlp_endpoint))

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
        registry: SkillRegistry | None = None,
    ) -> None:
        self.metabolism = metabolism
        self.market_service = market_service
        self.registry = registry

    async def Negotiate(
        self, request: Any, context: Any
    ) -> negotiation_pb2.NegotiateResponse:
        if not self.metabolism:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return negotiation_pb2.NegotiateResponse()

        request_id = str(
            extract_request_id(context)
            or getattr(request, "request_id", str(uuid.uuid4()))
        )
        bind_request_id(request_id)

        try:
            observation = await self.metabolism.execute(request)
            return observation.data  # type: ignore
        except Exception as e:
            logger.error("metabolic_failure", error=str(e), exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            return negotiation_pb2.NegotiateResponse()
        finally:
            clear_request_context()

    async def Search(self, request: Any, context: Any) -> negotiation_pb2.SearchResponse:
        if not self.registry:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return negotiation_pb2.SearchResponse()

        request_id = str(
            extract_request_id(context)
            or getattr(request, "request_id", str(uuid.uuid4()))
        )
        bind_request_id(request_id)

        try:
            reasoning = self.registry.get("reasoning")
            emb_obs = await reasoning.execute("generate_embedding", {"text": request.query})
            query_vector = emb_obs.data

            storage = self.registry.get("storage")
            obs = await storage.execute(
                "list_items_semantic_search",
                {
                    "query_vector": query_vector,
                    "limit": request.limit or 5,
                    "min_similarity": request.min_similarity,
                },
            )

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
            return negotiation_pb2.SearchResponse(results=response_items)
        except Exception as e:
            logger.error("search_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return negotiation_pb2.SearchResponse()
        finally:
            clear_request_context()

    async def GetSystemStatus(
        self, request: negotiation_pb2.GetSystemStatusRequest, context: Any
    ) -> negotiation_pb2.GetSystemStatusResponse:
        if not self.metabolism:
            return negotiation_pb2.GetSystemStatusResponse(status="initializing")
        vitals = await self.metabolism.aggregator.get_vitals()
        return negotiation_pb2.GetSystemStatusResponse(
            status=vitals.status,
            cpu_usage_percent=vitals.cpu_usage_percent,
            memory_usage_mb=vitals.memory_usage_mb,
            timestamp=vitals.timestamp,
            cached=vitals.cached,
        )

    async def CheckDealStatus(
        self, request: negotiation_pb2.CheckDealStatusRequest, context: Any
    ) -> negotiation_pb2.CheckDealStatusResponse:
        if not self.market_service:
             return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")
        return await self.market_service.check_status(deal_id=request.deal_id)


def create_crypto_protein() -> Any:
    if not settings.crypto.enabled:
        return None
    from hive.proteins.crypto import CryptoProtein
    return CryptoProtein(
        private_key_base58=get_raw_key(settings.crypto.solana_private_key),
        rpc_url=str(settings.crypto.solana_rpc_url),
        network=settings.crypto.solana_network,
        usdc_mint=settings.crypto.solana_usdc_mint,
    )


async def serve() -> None:
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.server.grpc_max_workers)
    )
    health_servicer = health_pb2_grpc.add_HealthServicer_to_server(
        health_pb2_grpc.health.HealthServicer(), server
    )
    negotiation_service = NegotiationService()
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        negotiation_service, server
    )
    server.add_insecure_port(f"[::]:{settings.server.port}")
    await server.start()

    # Metrics
    try:
        start_http_server(9091)
    except Exception:
        pass

    # NATS
    nc = None
    try:
        nc = await nats.connect(settings.server.nats_url)
    except Exception:
        logger.warning("nats_failed")

    # Proteins
    registry = SkillRegistry()
    from hive.proteins.storage import StorageProtein
    from hive.proteins.reasoning import ReasoningProtein
    from hive.proteins.telemetry import TelemetryProtein
    from hive.proteins.guard import GuardProtein
    from hive.proteins.pulse import PulseProtein

    storage = StorageProtein()
    reasoning = ReasoningProtein()
    telemetry = TelemetryProtein()
    guard = GuardProtein()
    pulse = PulseProtein()
    crypto = create_crypto_protein()

    await storage.execute("init_db", {})
    await asyncio.gather(
        storage.initialize(),
        reasoning.initialize(),
        telemetry.initialize(),
        guard.initialize(),
        pulse.initialize()
    )

    registry.register("storage", storage)
    registry.register("reasoning", reasoning)
    registry.register("telemetry", telemetry)
    registry.register("guard", guard)
    registry.register("pulse", pulse)
    if crypto:
        registry.register("crypto", crypto)

    # Market Service
    market_service = None
    if crypto:
        from hive.connector.proteins.encryption import SecretEncryption
        from hive.services.market import MarketService
        # Use re-exported encryption if available or use the protein's internal one
        # To be "pure" we should maybe have an encryption skill, but for now let's use the logic
        from hive.proteins.crypto._encryption import SecretEncryption
        encryption = SecretEncryption(get_raw_key(settings.crypto.secret_encryption_key))
        market_service = MarketService(storage=storage, crypto=crypto, encryption=encryption)

    # Nucleotides
    aggregator = HiveAggregator(registry=registry)
    transformer = AuraTransformer(registry=registry)
    connector = HiveConnector(registry=registry, market_service=market_service)
    generator = HiveGenerator(registry=registry)
    membrane = HiveMembrane(registry=registry)

    metabolism = MetabolicLoop(
        aggregator=aggregator, transformer=transformer,
        connector=connector, generator=generator, membrane=membrane
    )

    negotiation_service.metabolism = metabolism
    negotiation_service.registry = registry
    negotiation_service.market_service = market_service

    # Heartbeat loop
    async def heartbeat_loop():
        await asyncio.sleep(60)
        while True:
            try:
                obs = await storage.execute("get_first_item", {})
                if obs.success and obs.data:
                    item = obs.data
                    mock_signal = negotiation_pb2.NegotiateRequest(
                        item_id=item["id"],
                        bid_amount=item["base_price"] * settings.heartbeat.bid_multiplier,
                        currency_code="USD",
                        agent=negotiation_pb2.AgentIdentity(
                            did=settings.heartbeat.agent_did,
                            reputation_score=settings.heartbeat.agent_reputation,
                        ),
                        request_id=f"heartbeat-{uuid.uuid4()}",
                    )
                    await metabolism.execute(mock_signal)
            except Exception as e:
                logger.error("heartbeat_loop_failed", error=str(e))
            await asyncio.sleep(settings.heartbeat.interval_seconds)

    asyncio.create_task(heartbeat_loop())

    logger.info("hive_crystalline_state_attained")
    try:
        await server.wait_for_termination()
    finally:
        await pulse.close()
        if crypto: await crypto.close()

if __name__ == "__main__":
    asyncio.run(serve())
