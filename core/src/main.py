import asyncio
import uuid
from concurrent import futures

import grpc
import grpc.aio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from hive.metabolism.logging_config import configure_logging, get_logger
from hive.proteins.telemetry.enzymes.prometheus import init_telemetry
from hive.proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from prometheus_client import start_http_server

from config import settings
from server import NegotiationService
from metabolism_setup import setup_metabolism

configure_logging(log_level=settings.server.log_level)
logger = get_logger("core")

async def heartbeat_deal_loop(persistence_protein, metabolism) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            obs = await persistence_protein.execute("get_first_item", {})
            if obs.success and obs.item:
                item = obs.item
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
                await metabolism.execute(mock_signal, is_heartbeat=True)
        except Exception as e:
            logger.error("heartbeat_deal_error", error=str(e))
        await asyncio.sleep(settings.heartbeat.interval_seconds)

async def serve() -> None:
    init_telemetry(settings.server.otel_service_name, str(settings.server.otel_exporter_otlp_endpoint))
    GrpcInstrumentorServer().instrument()
    LangchainInstrumentor().instrument()

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=settings.server.grpc_max_workers))
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    metabolism, registry, market_service = await setup_metabolism()
    negotiation_service = NegotiationService(metabolism=metabolism, market_service=market_service)
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(negotiation_service, server)

    server.add_insecure_port(f"[::]:{settings.server.port}")
    await server.start()
    start_http_server(9091)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    asyncio.create_task(heartbeat_deal_loop(registry.get("persistence"), metabolism))
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
