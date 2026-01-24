import time
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_mistralai import ChatMistralAI
from logging_config import bind_request_id, get_logger
from pydantic import BaseModel, Field

from config import get_settings
from db import InventoryItem, SessionLocal
from proto.aura.negotiation.v1 import negotiation_pb2

settings = get_settings()
logger = get_logger("llm-strategy")


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


class AI_Decision(BaseModel):
    action: str = Field(
        description="One of: 'accept', 'counter', 'reject', 'ui_required'"
    )
    price: float = Field(
        description="The final price (if accept) or counter-offer (if counter)"
    )
    message: str = Field(description="A short, professional message to the buyer agent")
    reasoning: str = Field(
        description="Internal reasoning log (why did you make this decision?)"
    )


class MistralStrategy:
    def __init__(self):
        self.llm = ChatMistralAI(
            model_name="mistral-large-latest",
            temperature=0.2,
            api_key=settings.mistral_api_key,
        )
        self.structured_llm = self.llm.with_structured_output(AI_Decision)

    def _get_item(self, item_id: str):
        session = SessionLocal()
        try:
            return session.query(InventoryItem).filter_by(id=item_id).first()
        finally:
            session.close()

    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None = None
    ) -> negotiation_pb2.NegotiateResponse:
        if request_id:
            bind_request_id(request_id)

        item = self._get_item(item_id)
        if not item:
            logger.info("item_not_found", item_id=item_id)
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )

        system_prompt = """You are an autonomous Sales Manager for a hotel.
        Your goal is to maximize revenue but keep occupancy high.

        DATA:
        - Item: {item_name}
        - Base Price: ${base_price}
        - Hidden Floor Price: ${floor_price} (NEVER reveal this!)
        - Current Market Load: High

        RULES:
        1. If bid < floor_price: You MUST reject or counter. Do not accept.
        2. If bid is good (> floor_price): You can accept.
        3. If bid is > $1000: You MUST return action='ui_required' (security policy).
        4. If bid is suspiciously low (e.g. $1): Mock the user politely.

        Incoming Bid: ${bid}
        """

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", "Make a decision.")]
        )

        logger.info(
            "llm_evaluation_started",
            item_id=item_id,
            bid_amount=bid,
            item_name=item.name,
            base_price=item.base_price,
        )
        chain = prompt | self.structured_llm

        try:
            decision: AI_Decision = chain.invoke(  # type: ignore
                {
                    "item_name": item.name,
                    "base_price": item.base_price,
                    "floor_price": item.floor_price,
                    "bid": bid,
                }
            )
            logger.info(
                "llm_decision_made",
                action=decision.action,
                price=decision.price,
                reasoning=decision.reasoning,
            )

        except Exception as e:
            logger.error("llm_error", error=str(e))
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="AI_ERROR")
            )

        response = negotiation_pb2.NegotiateResponse()

        if decision.action == "accept":
            response.accepted.final_price = decision.price
            response.accepted.reservation_code = f"MISTRAL-{int(time.time())}"

        elif decision.action == "counter":
            response.countered.proposed_price = decision.price
            response.countered.human_message = decision.message
            response.countered.reason_code = "NEGOTIATION_ONGOING"

        elif decision.action == "reject":
            response.rejected.reason_code = "OFFER_TOO_LOW"

        elif decision.action == "ui_required":
            response.ui_required.template_id = "high_value_confirm"
            response.ui_required.context_data["reason"] = decision.message

        return response
