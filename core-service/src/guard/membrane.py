import structlog
from src.config import settings

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
            decision: Dict containing 'action', 'price', and optional 'addons'
            context: Dict containing 'floor_price', 'internal_cost', and 'base_price'

        Returns:
            True if decision is safe.

        Raises:
            SafetyViolation: If decision violates any guardrail.
        """
        action = decision.get("action")
        offered_price = decision.get("price", 0.0)

        # 1. Retrieve economic parameters from context
        floor_price = context.get("floor_price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)
        base_price = context.get("base_price", 0.0)

        # 1.5 Basic Validity Check
        if offered_price <= 0 and action in ["accept", "counter"]:
            logger.warning("invalid_offered_price", price=offered_price)
            raise SafetyViolation("Invalid offered price")

        # 2. Margin Check
        # User defined margin: (offered_price - internal_cost) / internal_cost
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
        elif internal_cost == 0:
            logger.warning("zero_internal_cost", action=action, price=offered_price)
            # We don't block here, but we warn as it might indicate data issues.

        # 3. Floor Price Violation
        # Check if action is "accept" but price < floor_price
        if action == "accept" and offered_price < floor_price:
            logger.warning(
                "safety_floor_violation",
                action=action,
                offered_price=offered_price,
                floor_price=floor_price,
            )
            raise SafetyViolation("Floor price breach")

        # 4. Maximum Discount Check
        if base_price > 0:
            discount = (base_price - offered_price) / base_price
            if discount > settings.safety.max_discount_percent:
                logger.warning(
                    "safety_discount_violation",
                    offered_price=offered_price,
                    base_price=base_price,
                    discount=discount,
                    max_discount=settings.safety.max_discount_percent,
                )
                raise SafetyViolation("Maximum discount exceeded")

        # 5. Allowed Addons Check
        addons = decision.get("addons", [])
        if isinstance(addons, list):
            for addon in addons:
                if addon not in settings.safety.allowed_addons:
                    logger.warning("safety_addon_violation", addon=addon)
                    raise SafetyViolation(f"Unsanctioned addon: {addon}")

        return True
