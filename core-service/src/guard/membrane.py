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

        # 2. Invalid Price Check
        if offered_price <= 0 and action in ["accept", "counter"]:
            logger.warning("invalid_offered_price", price=offered_price)
            raise SafetyViolation("Invalid offered price")

        # 3. Margin Check
        if internal_cost > 0:
            # Calculate margin based on internal cost (as requested)
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

        # 4. Floor Price Violation
        # Only check floor price breach if action is "accept" (as requested)
        if action == "accept" and offered_price < floor_price:
            logger.warning(
                "safety_floor_violation",
                action=action,
                offered_price=offered_price,
                floor_price=floor_price,
            )
            raise SafetyViolation("Floor price breach")

        # 5. Max Discount Check
        base_price = context.get("base_price", 0.0)
        if base_price > 0 and action in ["accept", "counter"]:
            discount = (base_price - offered_price) / base_price
            if discount > settings.safety.max_discount_percent:
                logger.warning(
                    "safety_discount_violation",
                    offered_price=offered_price,
                    base_price=base_price,
                    discount=discount,
                    max_discount=settings.safety.max_discount_percent,
                )
                raise SafetyViolation("Discount limit exceeded")

        # 6. Allowed Addons Check
        # If the LLM mentions something that looks like an addon, it must be in the allowed list.
        # This is a heuristic check for the "Membrane" pattern.
        if action in ["accept", "counter"] and decision.get("message"):
            msg = decision["message"].lower()
            # Derive the list of potential addons to look for from context and settings
            inventory = context.get("value_add_inventory", [])
            inventory_addons = [item.get("item", "").lower() for item in inventory if item.get("item")]
            configured_addons = [a.lower() for a in settings.safety.allowed_addons]

            # We check both what's in inventory and what's explicitly allowed in settings
            potential_addons = set(inventory_addons + configured_addons)

            for addon in potential_addons:
                if addon and addon in msg and addon not in configured_addons:
                    logger.warning("safety_addon_violation", addon=addon)
                    raise SafetyViolation(f"Unauthorized addon mentioned: {addon}")

        return True
