import time
from concurrent import futures
from typing import Protocol

import grpc

from config import get_settings
from db import InventoryItem, SessionLocal
from embeddings import generate_embedding
from llm_strategy import MistralStrategy
from logging_config import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

# Configure structured logging on startup
configure_logging()
logger = get_logger("core-service")

settings = get_settings()

# gRPC metadata key for request_id
REQUEST_ID_METADATA_KEY = "x-request-id"


def extract_request_id(context) -> str | None:
    """Extract request_id from gRPC metadata."""
    metadata = dict(context.invocation_metadata())
    return metadata.get(REQUEST_ID_METADATA_KEY)


class PricingStrategy(Protocol):
    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None
    ) -> negotiation_pb2.NegotiateResponse: ...


class NegotiationService(negotiation_pb2_grpc.NegotiationServiceServicer):
    def __init__(self, strategy: PricingStrategy):
        self.strategy = strategy

    def Negotiate(self, request, context):
        request_id = extract_request_id(context) or request.request_id
        bind_request_id(request_id)

        try:
            logger.info(
                "negotiate_request_received",
                item_id=request.item_id,
                bid_amount=request.bid_amount,
                agent_did=request.agent.did,
            )

            if request.bid_amount <= 0:
                logger.error(
                    "invalid_bid_amount",
                    bid_amount=request.bid_amount,
                    error="Bid amount must be positive",
                )
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Bid amount must be positive")
                return negotiation_pb2.NegotiateResponse()

            response = self.strategy.evaluate(
                item_id=request.item_id,
                bid=request.bid_amount,
                reputation=request.agent.reputation_score,
                request_id=request_id,
            )

            response.session_token = "sess_" + request.request_id
            response.valid_until_timestamp = int(time.time() + 600)

            logger.info(
                "negotiate_response_sent",
                session_token=response.session_token,
                result_type=response.WhichOneof("result"),
            )

            return response
        finally:
            clear_request_context()

    def Search(self, request, context):
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


def serve():
    strategy = MistralStrategy()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers)
    )
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        NegotiationService(strategy), server
    )

    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    logger.info("server_started", port=settings.grpc_port, database="postgres")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
