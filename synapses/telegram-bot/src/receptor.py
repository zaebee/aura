from dataclasses import dataclass
from enum import Enum
from typing import Any

import betterproto
import grpc
import structlog
from aura_core.gen.aura.negotiation.v1 import NegotiationServiceStub
from translator import TelegramTranslator

logger = structlog.get_logger(__name__)


class NegotiationStatus(Enum):
    SUCCESS = "success"
    COUNTERED = "countered"
    REJECTED = "rejected"
    UI_REQUIRED = "ui_required"
    ERROR = "error"


@dataclass
class StructuredResponse:
    text: str
    status: NegotiationStatus


class TelegramReceptor:
    """
    Afferent logic: External World (Telegram) -> Metabolism (Core gRPC).
    """

    def __init__(self, core_url: str) -> None:
        self.channel = grpc.aio.insecure_channel(core_url)
        self.stub = NegotiationServiceStub(self.channel)

    async def negotiate(self, message: Any, item_id: str, bid_amount: float) -> StructuredResponse:
        request = TelegramTranslator.to_negotiate_request(message, item_id, bid_amount)
        try:
            response = await self.stub.negotiate(
                request_id=request.request_id,
                item_id=request.item_id,
                bid_amount=request.bid_amount,
                currency_code=request.currency_code,
                agent=request.agent,
            )
            text = TelegramTranslator.from_negotiate_response(response)

            # Map gRPC result to our internal status
            result_type, _ = betterproto.which_one_of(response, "result")
            status_map = {
                "accepted": NegotiationStatus.SUCCESS,
                "countered": NegotiationStatus.COUNTERED,
                "rejected": NegotiationStatus.REJECTED,
                "ui_required": NegotiationStatus.UI_REQUIRED,
            }
            status = status_map.get(result_type, NegotiationStatus.ERROR)

            return StructuredResponse(text=text, status=status)

        except grpc.RpcError as e:
            logger.error("receptor_negotiate_grpc_error", code=e.code(), details=e.details())
            return StructuredResponse(
                text="Error: The negotiation service is currently unavailable. Please try again later.",
                status=NegotiationStatus.ERROR
            )
        except Exception as e:
            logger.error("receptor_negotiate_unexpected_error", error=str(e), exc_info=True)
            return StructuredResponse(
                text="An unexpected error occurred during negotiation.",
                status=NegotiationStatus.ERROR
            )

    async def search(self, query: str, limit: int = 5) -> str:
        request = TelegramTranslator.to_search_request(query, limit)
        try:
            response = await self.stub.search(
                query=request.query,
                limit=request.limit,
                min_similarity=request.min_similarity,
            )
            return TelegramTranslator.from_search_response(response)
        except grpc.RpcError as e:
            logger.error("receptor_search_grpc_error", code=e.code(), details=e.details())
            return "Error: Search service is currently unavailable."
        except Exception as e:
            logger.error("receptor_search_unexpected_error", error=str(e), exc_info=True)
            return "An unexpected error occurred during search."

    async def close(self) -> None:
        await self.channel.close()
