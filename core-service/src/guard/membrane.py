import structlog

from config import settings

logger = structlog.get_logger(__name__)


class SafetyViolation(Exception):
    """Raised when a negotiation decision violates safety guardrails."""

    pass


class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    """

    def validate_decision(self, decision: dict, context: dict) -> bool:
        """
        Validates a negotiation decision against economic guardrails.

        Args:
            decision: Dict containing 'action' and 'price'
            context: Dict containing 'floor_price' and 'internal_cost'

        Returns:
            True if decision is safe.

        Raises:
            SafetyViolation: If decision violates any guardrail.
        """
        action = decision.get("action")
        offered_price = decision.get("price", 0.0)

        # 1. Retrieve floor_price and internal_cost from context
        floor_price = context.get("floor_price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)

        # 2. Margin Check
        if internal_cost > 0:
            margin = (offered_price - internal_cost) / internal_cost
            if margin < settings.safety.min_profit_margin:
                logger.warning(
                    "safety_margin_violation",
                    offered_price=offered_price,
                    internal_cost=internal_cost,
                    margin=margin,
                    min_margin=settings.safety.min_profit_margin,
                )
                raise SafetyViolation("Economic suicide attempt")
        else:
            logger.warning("missing_internal_cost", item_id=context.get("item_id"))

        # 3. Floor Price Breach
        if action == "accept" and offered_price < floor_price:
            logger.warning(
                "safety_floor_breach",
                offered_price=offered_price,
                floor_price=floor_price,
            )
            raise SafetyViolation("Floor price breach")

        return True
