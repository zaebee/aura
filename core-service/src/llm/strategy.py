"""
LLM-based pricing strategy using litellm engine.

Supports any LLM provider (OpenAI, Mistral, Anthropic, Ollama, etc.) via litellm.
"""

import time
from pathlib import Path

import structlog
from jinja2 import Template
from llm.engine import LLMEngine
from logging_config import bind_request_id
from pydantic import BaseModel, Field

from db import InventoryItem, SessionLocal
from proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


class AI_Decision(BaseModel):
    """Structured output format for LLM negotiation decisions."""

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


class LiteLLMStrategy:
    """LLM-based pricing strategy with flexible model selection."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        trigger_price: float = 1000.0,
    ):
        """
        Initialize LiteLLM strategy.

        Args:
            model: Model identifier in litellm format (e.g., "openai/gpt-4o")
            temperature: Sampling temperature (0.0-1.0)
            api_key: Optional API key for the provider
            trigger_price: Security threshold for UI confirmation
        """
        self.engine = LLMEngine(
            model=model, temperature=temperature, api_key=api_key
        )
        self.trigger_price = trigger_price

        # Load prompt template
        template_path = Path(__file__).parent.parent / "prompts" / "system.md"
        with open(template_path) as f:
            self.prompt_template = Template(f.read())

        logger.info(
            "litellm_strategy_initialized",
            model=model,
            temperature=temperature,
            trigger_price=trigger_price,
        )

    def _get_item(self, item_id: str) -> InventoryItem | None:
        """Fetch item from database."""
        session = SessionLocal()
        try:
            return session.query(InventoryItem).filter_by(id=item_id).first()
        finally:
            session.close()

    def evaluate(
        self,
        item_id: str,
        bid: float,
        reputation: float,
        request_id: str | None = None,
    ) -> negotiation_pb2.NegotiateResponse:
        """
        Evaluate negotiation using LLM.

        Args:
            item_id: Item identifier
            bid: Proposed bid amount
            reputation: Agent reputation score
            request_id: Optional request ID for logging

        Returns:
            NegotiateResponse with decision (accept/counter/reject/ui_required)
        """
        if request_id:
            bind_request_id(request_id)

        item = self._get_item(item_id)
        if not item:
            logger.info("item_not_found", item_id=item_id)
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )

        # Render system prompt with item data
        system_prompt = self.prompt_template.render(
            business_type="hotel",
            item_name=item.name,
            base_price=item.base_price,
            floor_price=item.floor_price,
            market_load="High",
            trigger_price=self.trigger_price,
            bid=bid,
            reputation=reputation,
        )

        logger.info(
            "llm_evaluation_started",
            item_id=item_id,
            bid_amount=bid,
            item_name=item.name,
            base_price=item.base_price,
            model=self.engine.model,
        )

        try:
            # Call LLM with structured output
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Make a decision."},
            ]

            decision: AI_Decision = self.engine.complete(
                messages=messages,
                response_format=AI_Decision,
            )  # type: ignore

            logger.info(
                "llm_decision_made",
                action=decision.action,
                price=decision.price,
                reasoning=decision.reasoning,
            )

        except Exception as e:
            logger.error("llm_error", error=str(e), exc_info=True)
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="AI_ERROR")
            )

        # Map LLM decision to protobuf response
        response = negotiation_pb2.NegotiateResponse()

        if decision.action == "accept":
            response.accepted.final_price = decision.price
            response.accepted.reservation_code = (
                f"LLM-{self.engine.model.split('/')[0].upper()}-{int(time.time())}"
            )

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
