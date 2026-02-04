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
        action = decision.get("action")
        offered_price = decision.get("price", 0.0)
        floor_price = context.get("floor_price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)

        if action not in ["accept", "counter"]:
            return True

        # 1. Price non-positive check
        if offered_price <= 0:
            logger.warning("invalid_offered_price", extra={"price": offered_price})
            raise SafetyViolation("Invalid offered price")

        # 2. Floor price violation
        if offered_price < floor_price:
            logger.warning(
                "safety_floor_violation",
                extra={
                    "action": action,
                    "offered_price": offered_price,
                    "floor_price": floor_price,
                },
            )
            raise SafetyViolation("Floor price violation")

        # 3. Margin violation
        margin = (offered_price - internal_cost) / offered_price

        # DNA Rule: Safety Guard must "Fail-Closed" if misconfigured.
        if not self.settings:
            logger.error("guard_settings_missing_fail_closed")
            raise SafetyViolation(
                "Cannot validate margin: safety settings not provided."
            )

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
            raise SafetyViolation("Minimum profit margin violation")

        return True
