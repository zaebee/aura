import time
from concurrent import futures
from typing import Protocol

import grpc

from config import get_settings
from db import InventoryItem, SessionLocal
from embeddings import generate_embedding
from llm_strategy import MistralStrategy
from proto.aura.negotiation.v1 import negotiation_pb2, negotiation_pb2_grpc

settings = get_settings()


class PricingStrategy(Protocol):
    def evaluate(
        self, item_id: str, bid: float, reputation: float
    ) -> negotiation_pb2.NegotiateResponse: ...


class NegotiationService(negotiation_pb2_grpc.NegotiationServiceServicer):
    def __init__(self, strategy: PricingStrategy):
        self.strategy = strategy

    def Negotiate(self, request, context):
        if request.bid_amount <= 0:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Bid amount must be positive")
            return negotiation_pb2.NegotiateResponse()

        response = self.strategy.evaluate(
            item_id=request.item_id,
            bid=request.bid_amount,
            reputation=request.agent.reputation_score,
        )

        response.session_token = "sess_" + request.request_id
        response.valid_until_timestamp = int(time.time() + 600)
        return response

    def Search(self, request, context):
        """Реализация семантического поиска"""
        print(f"🔎 Searching for: '{request.query}'")

        # 1. Генерируем вектор запроса
        query_vector = generate_embedding(request.query)
        if not query_vector:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to generate embeddings")
            return negotiation_pb2.SearchResponse()

        # 2. Ищем в базе (Vector Search)
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

            return negotiation_pb2.SearchResponse(results=response_items)

        except Exception as e:
            print(f"🔥 DB Error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return negotiation_pb2.SearchResponse()

        finally:
            session.close()


def serve():
    strategy = MistralStrategy()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers)
    )
    negotiation_pb2_grpc.add_NegotiationServiceServicer_to_server(
        NegotiationService(strategy), server
    )

    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    print(f"gRPC Core Engine running on :{settings.grpc_port} (Connected to Postgres)")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
