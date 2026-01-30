"""
DSPy-based pricing strategy for Aura negotiation engine.

Implements the PricingStrategy protocol using the self-optimizing DSPy module.
"""

import time
from pathlib import Path

import dspy
import structlog
from guard.membrane import OutputGuard, SafetyViolation
from llm.engine import AuraNegotiator

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
        self.settings = get_settings()
        self.negotiator = self._load_compiled_program()
        self.guard = OutputGuard()
        self.fallback_strategy = None

        # Configure DSPy with litellm backend
        litellm_model = self.settings.llm.model
        dspy.configure(lm=dspy.LM(model=litellm_model))

        logger.info(
            "dspy_strategy_initialized",
            compiled_program=compiled_program_path,
            llm_model=litellm_model,
        )

    def _load_compiled_program(self):
        """Load compiled DSPy program with fallback to untrained module.

        Searches for the compiled brain in both src/ and data/ directories.
        """
        try:
            # The path from settings can be absolute or relative to the CWD.
            settings_path = Path(self.compiled_program_path)
            # Use only the filename part for searching in default locations.
            filename = settings_path.name

            # Define paths in search order.
            # 1. Path specified in settings (as-is).
            # 2. `data/` directory (new default for trained models).
            # 3. `src/` directory (legacy location).
            potential_paths = [
                settings_path,
                Path(__file__).parent.parent.parent / "data" / filename,
                Path(__file__).parent.parent / filename,
            ]

            for program_path in potential_paths:
                if program_path.exists() and program_path.is_file():
                    logger.info("Loading compiled DSPy program", path=str(program_path))
                    return dspy.load(str(program_path))

            logger.warning(
                "Compiled program not found in any search location, using untrained module",
                search_paths=[str(p) for p in potential_paths],
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

                self.fallback_strategy = LiteLLMStrategy(model=self.settings.llm.model)
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
        """Create standard economic context for DSPy module.

        Fetches dynamic context from item metadata if available.
        """
        # Default value-adds if not specified in metadata
        default_value_adds = [
            {"item": "Breakfast for two", "internal_cost": 20, "perceived_value": 60},
            {"item": "Late checkout", "internal_cost": 0, "perceived_value": 40},
            {"item": "Room upgrade", "internal_cost": 30, "perceived_value": 120},
        ]

        # Use item metadata for dynamic occupancy and perks
        meta = item.meta or {}

        return {
            "item_id": item.id,
            "base_price": item.base_price,
            "floor_price": item.floor_price,
            "internal_cost": meta.get("internal_cost", item.floor_price * 0.8),
            "occupancy": meta.get("occupancy", "medium"),
            "value_add_inventory": meta.get("value_add_inventory", default_value_adds),
        }

    def create_safe_counter_offer(
        self, item: InventoryItem, bid: float
    ) -> negotiation_pb2.NegotiateResponse:
        """Create a safe counter-offer at floor price when guardrails are hit."""
        result = negotiation_pb2.NegotiateResponse()
        result.countered.proposed_price = item.floor_price
        result.countered.human_message = (
            f"I cannot go that low. My best offer is {item.floor_price}."
        )
        result.countered.reason_code = "GUARDRAIL_INTERVENTION"
        return result

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
            # AuraNegotiator.forward now returns a clean dictionary with 'reasoning' and 'response'
            result = self.negotiator(
                input_bid=bid,
                context=context,
                history=[],  # Would include previous turns in multi-turn negotiation
            )

            response_data = result["response"]

            # Validate decision through the Membrane
            try:
                self.guard.validate_decision(response_data, context)
            except SafetyViolation as e:
                logger.warning(
                    "safety_guard_triggered",
                    item_id=item_id,
                    error=str(e),
                    llm_price=response_data.get("price"),
                )
                return self.create_safe_counter_offer(item, bid)

            action = response_data["action"]
            price = response_data["price"]
            message = response_data["message"]

            logger.info(
                "dspy_decision_made",
                action=action,
                price=price,
                item_id=item_id,
                reasoning_length=len(result.get("reasoning", "")),
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
