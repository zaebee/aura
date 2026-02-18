import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import betterproto
import grpclib.client
import nats
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from health import register_health_endpoints
from logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_current_request_id,
    get_logger,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel
from security import verify_signature
from starlette.middleware.cors import CORSMiddleware
from telemetry import init_telemetry

from config import get_settings

settings = get_settings()

# Configure structured logging on startup
configure_logging(log_level=settings.log_level)
logger = get_logger("api-gateway")

# Initialize OpenTelemetry tracing
service_name = settings.otel_service_name
tracer = init_telemetry(service_name, str(settings.otel_exporter_otlp_endpoint))

# Parse CORS origins
origins = [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]

# Declare globals
channel: grpclib.client.Channel
stub: Any  # NegotiationServiceStub — lazily imported in lifespan
_health_stub: Any | None = None
_health_channel: Any | None = None  # grpc.aio.Channel


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage grpclib and NATS lifecycle."""
    global channel, stub, _health_stub, _health_channel

    # --- Startup ---
    logger.info("startup_begin", service="api-gateway")

    # grpclib Channel for negotiation
    from aura_core_gen.aura.negotiation.v1 import NegotiationServiceStub

    host, port = settings.core_service_host.split(":")
    channel = grpclib.client.Channel(host, int(port))
    stub = NegotiationServiceStub(channel)

    # gRPC health stub (grpc.aio, separate channel)
    import grpc.aio
    from grpc_health.v1 import health_pb2_grpc as _health_pb2_grpc

    _health_channel = grpc.aio.insecure_channel(settings.core_service_host)
    _health_stub = _health_pb2_grpc.HealthStub(_health_channel)
    logger.info("health_stub_initialized", grpc_target=settings.core_service_host)

    # NATS Connection for Vision RPC
    app.state.nc = await nats.connect(settings.nats_url)

    logger.info(
        "startup_complete",
        grpc_target=settings.core_service_host,
    )

    try:
        yield
    finally:
        # --- Shutdown ---
        logger.info("shutdown_begin", service="api-gateway")
        if hasattr(app.state, "nc") and app.state.nc:
            await app.state.nc.drain()
            await app.state.nc.close()

        channel.close()  # Synchronous in grpclib

        if _health_channel is not None:
            await _health_channel.close()

        logger.info(
            "shutdown_complete", grpc_channel_closed=True, nats_connection_closed=True
        )


app = FastAPI(title="Aura Agent Gateway", version="1.0", lifespan=lifespan)

# Register health endpoints FIRST — before middleware and other routes
# so Kubernetes liveness probes respond immediately on process start.
register_health_endpoints(
    app,
    get_stub=lambda: _health_stub,
    health_check_timeout=settings.health_check_timeout,
    slow_threshold_ms=settings.health_check_slow_threshold_ms,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)

REQUEST_ID_METADATA_KEY = "x-request-id"


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = str(uuid.uuid4())
    bind_request_id(request_id)
    try:
        return await call_next(request)
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
    agent_did: str = Depends(verify_signature),
) -> dict[str, Any]:
    request_id = get_current_request_id() or str(uuid.uuid4())
    payload_dict = getattr(request.state, "parsed_body", {})
    payload = NegotiationRequestHTTP(**payload_dict)

    logger.info(
        "negotiate_request_received", item_id=payload.item_id, agent_did=agent_did
    )

    try:
        from aura_core_gen.aura.negotiation.v1 import (
            AgentIdentity as NegotiationAgentIdentity,
        )

        response = await stub.negotiate(
            request_id=request_id,
            item_id=payload.item_id,
            bid_amount=payload.bid_amount,
            currency_code=payload.currency,
            agent=NegotiationAgentIdentity(did=agent_did, reputation_score=1.0),
        )

        result_name, result_val = betterproto.which_one_of(response, "result")

        output = {
            "session_token": response.session_token,
            "status": result_name,
            "valid_until": response.valid_until_timestamp,
        }

        if result_name == "accepted" and result_val:
            reveal_name, reveal_val = betterproto.which_one_of(
                result_val, "reveal_method"
            )
            if reveal_name == "crypto_payment":
                payment = result_val.crypto_payment
                output["payment_required"] = True
                output["data"] = {
                    "final_price": result_val.final_price,
                    "payment_instructions": {
                        "deal_id": payment.deal_id,
                        "wallet_address": payment.wallet_address,
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "memo": payment.memo,
                        "network": payment.network,
                        "expires_at": payment.expires_at,
                    },
                }
            else:
                output["payment_required"] = False
                output["data"] = {
                    "final_price": result_val.final_price,
                    "reservation_code": result_val.reservation_code,
                }
        elif result_name == "countered" and result_val:
            output["data"] = {
                "proposed_price": result_val.proposed_price,
                "message": result_val.human_message,
            }
        elif result_name == "ui_required" and result_val:
            output["action_required"] = {
                "template": result_val.template_id,
                "context": dict(result_val.context_data),
            }

        return output

    except Exception as e:
        logger.error("negotiate_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Negotiation failed: {e}") from e


class SearchRequestHTTP(BaseModel):
    query: str
    limit: int = 3


@app.post("/v1/search")
async def search_items(
    request: Request, agent_did: str = Depends(verify_signature)
) -> dict[str, Any]:
    payload_dict = getattr(request.state, "parsed_body", {})
    payload = SearchRequestHTTP(**payload_dict)

    try:
        response = await stub.search(query=payload.query, limit=payload.limit)
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
        return {"results": results}
    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Search failed") from e


@app.get("/v1/system/status")
async def system_status() -> dict[str, Any]:
    try:
        response = await stub.get_system_status()
        return {
            "status": response.status,
            "cpu_usage_percent": response.cpu_usage_percent,
            "memory_usage_mb": response.memory_usage_mb,
            "timestamp": response.timestamp,
            "cached": response.cached,
        }
    except Exception as e:
        logger.error("status_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Monitoring unavailable") from e


@app.post("/v1/vision/analyze")
async def analyze_vision(
    request: Annotated[Request, Any],
    files: Annotated[list[UploadFile], File(...)],
    agent_did: Annotated[str, Depends(verify_signature)],
    focus: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    request_id = get_current_request_id() or str(uuid.uuid4())
    try:
        from aura_core_gen.aura.core.v1 import (
            AgentIdentity,
            PerceptionSignal,
            Signal,
            SignalType,
        )

        images_bytes = [await f.read() for f in files]
        signal = Signal(
            identifier=request_id,
            signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_PERCEPTION),
            timestamp=datetime.now(UTC),
            perception=PerceptionSignal(
                image_data=images_bytes,
                prompt=focus or settings.vision_default_prompt,
                agent=AgentIdentity(did=agent_did, reputation_score=1.0),
            ),
        )

        response = await request.app.state.nc.request(
            settings.vision_nats_subject,
            bytes(signal),
            timeout=settings.vision_rpc_timeout,
        )

        try:
            result = cast(dict[str, Any], json.loads(response.data.decode()))
        except Exception:
            from aura_core_gen.aura.core.v1 import Observation

            obs = Observation().parse(response.data)
            result = cast(
                dict[str, Any],
                obs.metadata.to_dict() if hasattr(obs.metadata, "to_dict") else {},
            )
            if not result and obs.error:
                result = {"error": obs.error}

        result["source"] = "vision-cortex"
        return result
    except Exception as e:
        logger.error("vision_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Vision analysis failed: {e}"
        ) from e


@app.post("/v1/deals/{deal_id}/status")
async def check_deal_status_endpoint(
    deal_id: str, agent_did: str = Depends(verify_signature)
) -> dict[str, Any]:
    try:
        response = await stub.check_deal_status(deal_id=deal_id)
        output: dict[str, Any] = {"status": response.status}

        if response.status == "PAID":
            output["secret"] = {
                "reservation_code": response.secret.reservation_code,
                "item_name": response.secret.item_name,
                "final_price": response.secret.final_price,
                "paid_at": response.secret.paid_at,
            }
            output["proof"] = {
                "transaction_hash": response.proof.transaction_hash,
                "block_number": response.proof.block_number,
                "from_address": response.proof.from_address,
                "confirmed_at": response.proof.confirmed_at,
            }
        elif response.status == "PENDING":
            payment = response.payment_instructions
            output["payment_instructions"] = {
                "deal_id": payment.deal_id,
                "wallet_address": payment.wallet_address,
                "amount": payment.amount,
                "currency": payment.currency,
                "memo": payment.memo,
                "network": payment.network,
                "expires_at": payment.expires_at,
            }
        return output
    except Exception as e:
        logger.error("check_deal_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Check deal failed") from e
