import logging
from typing import Any

logger = logging.getLogger(__name__)


class SafetyViolation(Exception):
    """Raised when a negotiation decision violates safety guardrails."""

    pass


class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    """

    def __init__(self, safety_settings: Any = None):
        self.settings = safety_settings

    def validate_decision(self, decision: dict, context: dict) -> bool:
        """
        Validate a negotiation decision against economic guardrails.

        Logic:
        - Calculate offered_price.
        - Retrieve floor_price, internal_cost, and base_price from context.
        - margin = (offered_price - internal_cost) / internal_cost.
        - If margin < settings.min_profit_margin: Raise SafetyViolation("Economic suicide attempt").
        - If action is "accept" but price < floor_price: Raise SafetyViolation("Floor price breach").
        - If discount > max_discount_percent: Raise SafetyViolation("Discount limit exceeded").
        - If addons in metadata are not in allowed_addons: Raise SafetyViolation("Unsanctioned addon").
        """
        action = decision.get("action")
        offered_price = float(decision.get("price", 0.0))
        floor_price = float(context.get("floor_price", 0.0))
        internal_cost = float(context.get("internal_cost", 0.0))
        base_price = float(context.get("base_price", 0.0))

        if action not in ["accept", "counter"]:
            return True

        # 1. Floor price breach
        if action == "accept" and offered_price < floor_price:
            logger.warning(
                "safety_floor_breach",
                extra={
                    "action": action,
                    "offered_price": offered_price,
                    "floor_price": floor_price,
                },
            )
            raise SafetyViolation("Floor price breach")

        # 2. Margin violation
        if internal_cost > 0:
            margin = (offered_price - internal_cost) / internal_cost
        else:
            margin = 1.0 if offered_price > 0 else -1.0

        min_margin = 0.10
        if self.settings and hasattr(self.settings, "min_profit_margin"):
            min_margin = self.settings.min_profit_margin

        if margin < min_margin:
            logger.warning(
                "safety_margin_violation",
                extra={
                    "offered_price": offered_price,
                    "internal_cost": internal_cost,
                    "margin": margin,
                    "min_margin": min_margin,
                },
            )
            raise SafetyViolation("Economic suicide attempt")

        # 3. Discount limit
        if base_price > 0:
            discount = (base_price - offered_price) / base_price
            max_discount = 0.30
            if self.settings and hasattr(self.settings, "max_discount_percent"):
                max_discount = self.settings.max_discount_percent

            if discount > max_discount:
                logger.warning(
                    "safety_discount_violation",
                    extra={
                        "offered_price": offered_price,
                        "base_price": base_price,
                        "discount": discount,
                        "max_discount": max_discount,
                    },
                )
                raise SafetyViolation("Discount limit exceeded")

        # 4. Allowed addons
        decision_metadata = decision.get("metadata", {})
        if isinstance(decision_metadata, dict):
            addons = decision_metadata.get("addons", [])
            if addons:
                allowed_addons = []
                if self.settings and hasattr(self.settings, "allowed_addons"):
                    allowed_addons = self.settings.allowed_addons

                for addon in addons:
                    if addon not in allowed_addons:
                        logger.warning("safety_addon_violation", extra={"addon": addon})
                        raise SafetyViolation(f"Unsanctioned addon: {addon}")

        return True
