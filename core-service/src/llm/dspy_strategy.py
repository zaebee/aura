"""
DSPy-based pricing strategy for Aura negotiation engine.

Implements the PricingStrategy protocol using the self-optimizing DSPy module.
"""

import time
from pathlib import Path

import dspy
import structlog
from llm.engine import AuraNegotiator
from llm.prepare.clean import clean_and_parse_json

from config import get_settings
from db import InventoryItem, SessionLocal
from proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


class DSPyStrategy:
    """DSPy-based pricing strategy with self-optimizing negotiation.

    This strategy uses the compiled DSPy negotiator for decision making,
    with fallback to existing strategies for reliability.
    """

    def __init__(self, compiled_program_path: str = "aura_brain.json"):
        """Initialize DSPy strategy with compiled program.

        Args:
            compiled_program_path: Path to compiled DSPy program
        """
        self.compiled_program_path = compiled_program_path
        self.negotiator = self._load_compiled_program()
        self.settings = get_settings()
        self.fallback_strategy = None

        # Configure DSPy with litellm backend
        litellm_model = self.settings.llm_model
        dspy.configure(lm=litellm_model)

        logger.info(
            "dspy_strategy_initialized",
            compiled_program=compiled_program_path,
            llm_model=litellm_model,
        )

    def _load_compiled_program(self):
        """Load compiled DSPy program with fallback to untrained module."""
        try:
            program_path = Path(self.compiled_program_path)
            if program_path.exists():
                logger.info("Loading compiled DSPy program", path=str(program_path))
                return dspy.load(str(program_path))
            else:
                logger.warning(
                    "Compiled program not found, using untrained module",
                    path=str(program_path),
                )
                return AuraNegotiator()
        except Exception as e:
            logger.error("Failed to load compiled program", error=str(e))
            return AuraNegotiator()

    def _get_fallback_strategy(self):
        """Get fallback strategy (lazy loading)."""
        if self.fallback_strategy is None:
            try:
                from llm.strategy import LiteLLMStrategy

                self.fallback_strategy = LiteLLMStrategy(model=self.settings.llm_model)
            except ImportError:
                from llm_strategy import RuleBasedStrategy

                self.fallback_strategy = RuleBasedStrategy()
        return self.fallback_strategy

    def _get_item(self, item_id: str) -> InventoryItem | None:
        """Fetch item from database."""
        session = SessionLocal()
        try:
            return session.query(InventoryItem).filter_by(id=item_id).first()
        finally:
            session.close()

    def _create_standard_context(self, item: InventoryItem) -> dict:
        """Create standard economic context for DSPy module."""
        return {
            "base_price": item.base_price,
            "floor_price": item.floor_price,
            "occupancy": "high",  # Could be made dynamic based on current inventory
            "value_add_inventory": [
                {
                    "item": "Breakfast for two",
                    "internal_cost": 20,
                    "perceived_value": 60,
                },
                {"item": "Late checkout", "internal_cost": 0, "perceived_value": 40},
                {"item": "Room upgrade", "internal_cost": 30, "perceived_value": 120},
            ],
        }

    def evaluate(
        self,
        item_id: str,
        bid: float,
        reputation: float,
        request_id: str | None = None,
    ) -> negotiation_pb2.NegotiateResponse:
        """Evaluate negotiation using DSPy module.

        Args:
            item_id: Item identifier
            bid: Proposed bid amount
            reputation: Agent reputation score
            request_id: Optional request ID for logging

        Returns:
            NegotiateResponse with decision (accept/counter/reject)
        """
        logger.info(
            "dspy_evaluation_started",
            item_id=item_id,
            bid_amount=bid,
            request_id=request_id,
        )

        # Get item from database
        item = self._get_item(item_id)
        if not item:
            logger.info("item_not_found", item_id=item_id)
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )

        # Prepare context for DSPy
        context = self._create_standard_context(item)

        # Get prediction from DSPy module
        try:
            prediction = self.negotiator(
                input_bid=bid,
                context=context,
                history=[],  # Would include previous turns in multi-turn negotiation
            )

            # Parse response using robust JSON extraction
            try:
                raw_response = prediction.response
                if isinstance(raw_response, str):
                    response_data = clean_and_parse_json(raw_response)
                elif isinstance(raw_response, dict):
                    response_data = raw_response
                else:
                    raise ValueError(f"Unexpected response type: {type(raw_response)}")

                action = response_data["action"]
                price = response_data["price"]
                message = response_data["message"]
            except Exception as e:
                logger.error(
                    "dspy_response_parse_error",
                    error=str(e),
                    raw_response=prediction.response
                    if hasattr(prediction, "response")
                    else "N/A",
                    item_id=item_id,
                    bid_amount=bid,
                )
                # Fallback to rule-based strategy on parsing error
                return self._get_fallback_strategy().evaluate(
                    item_id, bid, reputation, request_id
                )

            logger.info(
                "dspy_decision_made",
                action=action,
                price=price,
                item_id=item_id,
                reasoning_length=len(prediction.reasoning),
            )

            # Map to protobuf response
            result = negotiation_pb2.NegotiateResponse()

            if action == "accept":
                result.accepted.final_price = price
                result.accepted.reservation_code = f"DSPY-{int(time.time())}"

            elif action == "counter":
                result.countered.proposed_price = price
                result.countered.human_message = message
                result.countered.reason_code = "NEGOTIATION_ONGOING"

            elif action == "reject":
                result.rejected.reason_code = "OFFER_TOO_LOW"

            else:
                # Unknown action - fallback to existing strategy
                logger.warning("unknown_dspy_action", action=action)
                return self._get_fallback_strategy().evaluate(
                    item_id, bid, reputation, request_id
                )

            return result

        except Exception as e:
            logger.error("dspy_evaluation_error", error=str(e), exc_info=True)
            # Fallback to existing strategy on error
            return self._get_fallback_strategy().evaluate(
                item_id, bid, reputation, request_id
            )
