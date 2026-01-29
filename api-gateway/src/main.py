import uuid
from contextlib import asynccontextmanager

import grpc
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from grpc_health.v1 import health_pb2_grpc
from logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_current_request_id,
    get_logger,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from telemetry import init_telemetry

from config import get_settings
from proto.aura.negotiation.v1 import (
    negotiation_pb2,  # type: ignore
    negotiation_pb2_grpc,  # type: ignore
)
from src.health import register_health_endpoints
from src.security import verify_signature

# Configure structured logging on startup
configure_logging()
logger = get_logger("api-gateway")

settings = get_settings()

# Initialize OpenTelemetry tracing
service_name = settings.otel_service_name
tracer = init_telemetry(service_name, settings.otel_exporter_otlp_endpoint)
logger.info(
    "telemetry_initialized",
    service_name=service_name,
    endpoint=settings.otel_exporter_otlp_endpoint,
)

# Parse CORS origins from settings (comma-separated string to list)
origins = [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]
logger.info("cors_configured", allowed_origins=origins)

# Instrument gRPC client for distributed tracing
GrpcInstrumentorClient().instrument()

# Declare globals that will be initialized during startup
channel: grpc.aio.Channel
stub: negotiation_pb2_grpc.NegotiationServiceStub
health_stub: health_pb2_grpc.HealthStub


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage gRPC channel lifecycle (startup and shutdown)."""
    global channel, stub, health_stub

    # --- Startup ---
    logger.info("startup_begin", service="api-gateway")
    channel = grpc.aio.insecure_channel(settings.core_service_host)
    stub = negotiation_pb2_grpc.NegotiationServiceStub(channel)
    health_stub = health_pb2_grpc.HealthStub(channel)

    # Register health check endpoints
    register_health_endpoints(
        app,
        health_stub,
        health_check_timeout=settings.health_check_timeout,
        slow_threshold_ms=settings.health_check_slow_threshold_ms,
    )

    logger.info(
        "startup_complete",
        grpc_target=settings.core_service_host,
        health_endpoints_registered=True,
    )

    try:
        yield
    finally:
        # --- Shutdown ---
        logger.info("shutdown_begin", service="api-gateway")
        await channel.close()
        logger.info("shutdown_complete", grpc_channel_closed=True)


# Initialize FastAPI with lifespan manager
app = FastAPI(title="Aura Agent Gateway", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI for automatic tracing
FastAPIInstrumentor.instrument_app(app)

# gRPC metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Middleware to generate and bind request_id for every HTTP request."""
    request_id = str(uuid.uuid4())
    bind_request_id(request_id)
    logger.info("request_started", method=request.method, path=str(request.url.path))
    try:
        response = await call_next(request)
        logger.info(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
        )
        return response
    except Exception as e:
        logger.error(
            "request_failed",
            method=request.method,
            path=str(request.url.path),
            error=str(e),
        )
        raise
    finally:
        clear_request_context()


class NegotiationRequestHTTP(BaseModel):
    item_id: str
    bid_amount: float
    currency: str = "USD"
    agent_did: str


@app.post("/v1/negotiate")
async def negotiate(
    request: Request,
    x_agent_token: str | None = Header(None),
    agent_did: str = Depends(verify_signature),
):
    request_id = get_current_request_id() or str(uuid.uuid4())

    # Get the parsed body from request.state (stored by verify_signature)
    payload_dict = getattr(request.state, "parsed_body", {})
    payload = NegotiationRequestHTTP(**payload_dict)

    logger.info(
        "negotiate_request_received",
        item_id=payload.item_id,
        bid_amount=payload.bid_amount,
        currency=payload.currency,
        agent_did=agent_did,  # Use the verified agent_did
    )

    # Auth Check: Signature verification is now handled by the verify_signature dependency
    # The agent_did parameter contains the verified DID from the security headers

    # Convert HTTP -> gRPC (Mapping)
    grpc_request = negotiation_pb2.NegotiateRequest(
        request_id=request_id,
        item_id=payload.item_id,
        bid_amount=payload.bid_amount,
        currency_code=payload.currency,
        agent=negotiation_pb2.AgentIdentity(
            did=agent_did,  # Use the verified agent_did from security headers
            reputation_score=1.0,
        ),
    )

    metadata = [(REQUEST_ID_METADATA_KEY, request_id)]

    try:
        logger.info(
            "grpc_call_started", service="NegotiationService", method="Negotiate"
        )
        response = await stub.Negotiate(grpc_request, metadata=metadata)
        logger.info(
            "grpc_call_completed", service="NegotiationService", method="Negotiate"
        )
        result_type = response.WhichOneof("result")

        output = {
            "session_token": response.session_token,
            "status": result_type,
            "valid_until": response.valid_until_timestamp,
        }

        if result_type == "accepted":
            output["data"] = {
                "final_price": response.accepted.final_price,
                "reservation_code": response.accepted.reservation_code,
            }
            logger.info(
                "negotiation_accepted",
                final_price=response.accepted.final_price,
                reservation_code=response.accepted.reservation_code,
            )
        elif result_type == "countered":
            output["data"] = {
                "proposed_price": response.countered.proposed_price,
                "message": response.countered.human_message,
            }
            logger.info(
                "negotiation_countered",
                proposed_price=response.countered.proposed_price,
            )
        elif result_type == "ui_required":
            output["action_required"] = {
                "template": response.ui_required.template_id,
                "context": dict(response.ui_required.context_data),
            }
            logger.info(
                "negotiation_ui_required",
                template_id=response.ui_required.template_id,
            )
        elif result_type == "rejected":
            logger.info("negotiation_rejected")

        return output

    except grpc.RpcError as e:
        logger.error(
            "grpc_call_failed",
            service="NegotiationService",
            method="Negotiate",
            error=e.details(),
            code=str(e.code()),
        )
        raise HTTPException(status_code=500, detail="Core service error") from e


class SearchRequestHTTP(BaseModel):
    query: str
    limit: int = 3


@app.post("/v1/search")
async def search_items(request: Request, agent_did: str = Depends(verify_signature)):
    request_id = get_current_request_id() or str(uuid.uuid4())

    # Get the parsed body from request.state (stored by verify_signature)
    payload_dict = getattr(request.state, "parsed_body", {})
    payload = SearchRequestHTTP(**payload_dict)

    logger.info(
        "search_request_received",
        query=payload.query,
        limit=payload.limit,
        agent_did=agent_did,
    )

    grpc_req = negotiation_pb2.SearchRequest(query=payload.query, limit=payload.limit)

    # Prepare gRPC metadata with request_id for tracing
    metadata = [(REQUEST_ID_METADATA_KEY, request_id)]

    try:
        logger.info("grpc_call_started", service="NegotiationService", method="Search")
        response = await stub.Search(grpc_req, metadata=metadata)
        logger.info(
            "grpc_call_completed",
            service="NegotiationService",
            method="Search",
            result_count=len(response.results),
        )
        results = [
            {
                "id": r.item_id,
                "name": r.name,
                "price": r.base_price,
                "score": round(r.similarity_score, 4),
                "details": r.description_snippet,
            }
            for r in response.results
        ]

        logger.info("search_completed", result_count=len(results))

        return {"results": results}

    except grpc.RpcError as e:
        logger.error(
            "grpc_call_failed",
            service="NegotiationService",
            method="Search",
            error=e.details(),
            code=str(e.code()),
        )
        raise HTTPException(status_code=500, detail="Core service search error") from e


@app.get("/v1/system/status")
async def system_status():
    """
    Expose internal infrastructure metrics.

    Returns cluster resource usage (CPU, memory) from Prometheus.
    """
    try:
        grpc_request = negotiation_pb2.GetSystemStatusRequest()
        response = await stub.GetSystemStatus(grpc_request)

        return {
            "status": response.status,
            "cpu_usage_percent": response.cpu_usage_percent,
            "memory_usage_mb": response.memory_usage_mb,
            "timestamp": response.timestamp,
            "cached": response.cached,
        }
    except grpc.RpcError as e:
        logger.error("system_status_grpc_error", error=e.details())
        raise HTTPException(
            status_code=500, detail="Monitoring service unavailable"
        ) from e
