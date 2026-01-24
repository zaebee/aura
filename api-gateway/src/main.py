import logging
import secrets

import grpc
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from config import get_settings
from proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="Aura Agent Gateway", version="1.0")

channel = grpc.insecure_channel(settings.core_service_host)
stub = negotiation_pb2_grpc.NegotiationServiceStub(channel)


# Pydantic Model (для Swagger UI и валидации JSON)
class NegotiationRequestHTTP(BaseModel):
    item_id: str
    bid_amount: float
    currency: str = "USD"
    agent_did: str


@app.post("/v1/negotiate")
async def negotiate(
    payload: NegotiationRequestHTTP,
    x_agent_token: str | None = Header(None),  # Auth Layer
):
    # 1. Auth Check (Здесь могла бы быть проверка JWT)
    if not x_agent_token:
        # Для PoC пропускаем, но в проде - 401
        pass

    # 2. Convert HTTP -> gRPC (Mapping)
    grpc_request = negotiation_pb2.NegotiateRequest(
        request_id="req_" + secrets.token_hex(4),
        item_id=payload.item_id,
        bid_amount=payload.bid_amount,
        currency_code=payload.currency,
        agent=negotiation_pb2.AgentIdentity(
            did=payload.agent_did,
            reputation_score=1.0,  # Заглушка, в реальности берем из Identity Service
        ),
    )

    try:
        # 3. Call Core Service
        response = stub.Negotiate(grpc_request)

        # 4. Convert gRPC -> HTTP (Mapping)
        # Ручной маппинг надежнее автоматического для публичного API
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
        elif result_type == "countered":
            output["data"] = {
                "proposed_price": response.countered.proposed_price,
                "message": response.countered.human_message,
            }
        elif result_type == "ui_required":
            output["action_required"] = {
                "template": response.ui_required.template_id,
                "context": dict(response.ui_required.context_data),
            }

        return output

    except grpc.RpcError as e:
        logger.exception("gRPC error during negotiation: %s", e.details())
        raise HTTPException(status_code=500, detail="Core service error") from e


class SearchRequestHTTP(BaseModel):
    query: str
    limit: int = 3


@app.post("/v1/search")
async def search_items(payload: SearchRequestHTTP):
    grpc_req = negotiation_pb2.SearchRequest(query=payload.query, limit=payload.limit)

    try:
        response = stub.Search(grpc_req)
        return {
            "results": [
                {
                    "id": r.item_id,
                    "name": r.name,
                    "price": r.base_price,
                    "score": round(r.similarity_score, 4),
                    "details": r.description_snippet,
                }
                for r in response.results
            ]
        }
    except grpc.RpcError as e:
        logger.exception("gRPC error during search: %s", e)
        raise HTTPException(status_code=500, detail="Core service search error") from e
