import uuid

import grpc
from fastapi import FastAPI, Header, HTTPException, Request
from google.protobuf.json_format import MessageToDict
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
from telemetry import init_telemetry

from config import get_settings
from proto.aura.negotiation.v1 import (
    negotiation_pb2,  # type: ignore
    negotiation_pb2_grpc,  # type: ignore
)

# Configure structured logging on startup
configure_logging()
logger = get_logger("api-gateway")

settings = get_settings()

# Initialize OpenTelemetry tracing
service_name = settings.otel_service_name
tracer = init_telemetry(service_name, settings.otel_exporter_otlp_endpoint)
logger.info("telemetry_initialized", service_name=service_name, endpoint=settings.otel_exporter_otlp_endpoint)

app = FastAPI(title="Aura Agent Gateway", version="1.0")

# Instrument FastAPI for automatic tracing
FastAPIInstrumentor.instrument_app(app)

# Instrument gRPC client for distributed tracing
GrpcInstrumentorClient().instrument()

channel = grpc.insecure_channel(settings.core_service_host)
stub = negotiation_pb2_grpc.NegotiationServiceStub(channel)

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
    payload: NegotiationRequestHTTP,
    x_agent_token: str | None = Header(None),
):
    request_id = get_current_request_id() or str(uuid.uuid4())

    logger.info(
        "negotiate_request_received",
        item_id=payload.item_id,
        bid_amount=payload.bid_amount,
        currency=payload.currency,
        agent_did=payload.agent_did,
    )

    # Auth Check (JWT verification would go here in production)
    if not x_agent_token:
        pass

    # Convert HTTP -> gRPC (Mapping)
    grpc_request = negotiation_pb2.NegotiateRequest(
        request_id=request_id,
        item_id=payload.item_id,
        bid_amount=payload.bid_amount,
        currency_code=payload.currency,
        agent=negotiation_pb2.AgentIdentity(
            did=payload.agent_did,
            reputation_score=1.0,
        ),
    )

    metadata = [(REQUEST_ID_METADATA_KEY, request_id)]

    try:
        logger.info(
            "grpc_call_started", service="NegotiationService", method="Negotiate"
        )
        response = stub.Negotiate(grpc_request, metadata=metadata)
        logger.info(
            "grpc_call_completed", service="NegotiationService", method="Negotiate"
        )
        result_type = response.WhichOneof("result")

        if result_type == "accepted":
            logger.info(
                "negotiation_accepted",
                final_price=response.accepted.final_price,
                reservation_code=response.accepted.reservation_code,
            )
        elif result_type == "countered":
            logger.info(
                "negotiation_countered",
                proposed_price=response.countered.proposed_price,
            )
        elif result_type == "ui_required":
            logger.info(
                "negotiation_ui_required",
                template_id=response.ui_required.template_id,
            )
        elif result_type == "rejected":
            logger.info("negotiation_rejected")

        return MessageToDict(
            response, preserving_proto_field_name=False, use_integers_for_enums=False
        )

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
async def search_items(payload: SearchRequestHTTP):
    request_id = get_current_request_id() or str(uuid.uuid4())

    logger.info(
        "search_request_received",
        query=payload.query,
        limit=payload.limit,
    )

    grpc_req = negotiation_pb2.SearchRequest(query=payload.query, limit=payload.limit)

    # Prepare gRPC metadata with request_id for tracing
    metadata = [(REQUEST_ID_METADATA_KEY, request_id)]

    try:
        logger.info("grpc_call_started", service="NegotiationService", method="Search")
        response = stub.Search(grpc_req, metadata=metadata)
        logger.info(
            "grpc_call_completed",
            service="NegotiationService",
            method="Search",
            result_count=len(response.results),
        )
        logger.info("search_completed", result_count=len(response.results))
        return MessageToDict(
            response, preserving_proto_field_name=False, use_integers_for_enums=False
        )

    except grpc.RpcError as e:
        logger.error(
            "grpc_call_failed",
            service="NegotiationService",
            method="Search",
            error=e.details(),
            code=str(e.code()),
        )
        raise HTTPException(status_code=500, detail="Core service search error") from e
