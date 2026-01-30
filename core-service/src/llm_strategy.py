import time
from typing import Protocol

from src.db import InventoryItem, SessionLocal
from src.logging_config import bind_request_id, get_logger
from src.proto.aura.negotiation.v1 import negotiation_pb2

logger = get_logger("rule-strategy")


class ItemRepository(Protocol):
    """Protocol for item repository to enable dependency injection."""

    def get_item(self, item_id: str) -> InventoryItem | None: ...


class DatabaseItemRepository:
    """Default repository implementation using the database."""

    def get_item(self, item_id: str) -> InventoryItem | None:
        session = SessionLocal()
        try:
            return session.query(InventoryItem).filter_by(id=item_id).first()
        finally:
            session.close()


class RuleBasedStrategy:
    """Rule-based pricing strategy that doesn't require an LLM.

    Rules:
    1. If bid < floor_price: Counter with floor_price
    2. If bid >= floor_price and bid < base_price: Accept
    3. If bid >= base_price: Accept
    4. If bid > trigger_price (default 1000): UI required (security policy)
    """

    def __init__(
        self,
        repository: ItemRepository | None = None,
        trigger_price: float = 1000.0,
    ):
        self.repository = repository or DatabaseItemRepository()
        self.trigger_price = trigger_price

    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None = None
    ) -> negotiation_pb2.NegotiateResponse:
        if request_id:
            bind_request_id(request_id)

        item = self.repository.get_item(item_id)
        if not item:
            logger.info("item_not_found", item_id=item_id)
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )

        logger.info(
            "rule_evaluation_started",
            item_id=item_id,
            bid_amount=bid,
            item_name=item.name,
            base_price=item.base_price,
            floor_price=item.floor_price,
        )

        response = negotiation_pb2.NegotiateResponse()

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            logger.info("ui_required_high_value", bid=bid, trigger=self.trigger_price)
            response.ui_required.template_id = "high_value_confirm"
            response.ui_required.context_data["reason"] = (
                f"Bid of ${bid} exceeds security threshold"
            )
            return response

        # Rule: Bid below floor price - counter with floor price
        if bid < item.floor_price:
            logger.info(
                "counter_offer",
                bid=bid,
                floor_price=item.floor_price,
            )
            response.countered.proposed_price = item.floor_price
            response.countered.human_message = (
                f"We cannot accept less than ${item.floor_price}."
            )
            response.countered.reason_code = "BELOW_FLOOR"
            return response

        # Rule: Bid at or above floor price - accept
        logger.info("offer_accepted", bid=bid, floor_price=item.floor_price)
        response.accepted.final_price = bid
        response.accepted.reservation_code = f"RULE-{int(time.time())}"
        return response
