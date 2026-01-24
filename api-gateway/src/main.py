import secrets
import uuid

import grpc
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from config import get_settings
from logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_current_request_id,
    get_logger,
)
from proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

# Configure structured logging on startup
configure_logging()
logger = get_logger("api-gateway")

settings = get_settings()

app = FastAPI(title="Aura Agent Gateway", version="1.0")

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
            "request_failed", method=request.method, path=str(request.url.path), error=str(e)
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

    # Prepare gRPC metadata with request_id for tracing
    metadata = [(REQUEST_ID_METADATA_KEY, request_id)]

    try:
        logger.info("grpc_call_started", service="NegotiationService", method="Negotiate")
        response = stub.Negotiate(grpc_request, metadata=metadata)
        logger.info("grpc_call_completed", service="NegotiationService", method="Negotiate")

        # Convert gRPC -> HTTP (Mapping)
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
