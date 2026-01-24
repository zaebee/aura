import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel, Field

from config import get_settings
from db import InventoryItem, SessionLocal
from logging_config import bind_request_id, get_logger
from proto.aura.negotiation.v1 import negotiation_pb2

settings = get_settings()
logger = get_logger("llm-strategy")


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
