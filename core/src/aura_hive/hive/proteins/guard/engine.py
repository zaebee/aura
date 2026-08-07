from typing import Any

import structlog

from aura_hive.hive.metabolism.math import HillDampener

logger = structlog.get_logger(__name__)


class SafetyViolation(Exception):
    """Raised when a negotiation decision violates safety guardrails."""

    pass


class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    (The "Greedy Merchant" fix)
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
            logger.warning("invalid_offered_price", price=offered_price)
            raise SafetyViolation("Invalid offered price")

        # 2. Floor price violation (Metabolic Leakage Protection)
        if offered_price < floor_price:
            logger.warning(
                "safety_floor_violation",
                action=action,
                offered_price=offered_price,
                floor_price=floor_price,
            )
            raise SafetyViolation("Metabolic Leakage: Amount below floor price")

        # 3. Margin violation
        if offered_price > 0:
            margin = (offered_price - internal_cost) / offered_price
        else:
            margin = 0

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
                offered_price=offered_price,
                internal_cost=internal_cost,
                margin=margin,
                min_margin=min_margin,
            )
            raise SafetyViolation("Minimum profit margin violation")

        return True

    def calculate_safe_price(self, context: dict, reason: str) -> float:
        """Deterministic safe price calculation for override."""
        floor = float(context.get("floor_price", 0.0))
        if "margin" in reason.lower():
            min_m = 0.1
            if self.settings:
                min_m = float(self.settings.min_profit_margin)

            if min_m >= 1.0:
                min_m = 0.1
            return float(round(floor / (1 - min_m), 2))
        return float(round(floor * 1.05, 2))

    def validate_transaction(
        self,
        wallet_address: str,
        llm_price: float,
        bid: float,
        base_price: float,
        is_sanctified: bool,
    ) -> float:
        """Validate a transaction: require sanctified wallet, apply Hill dampening ceiling."""
        if not is_sanctified:
            raise SafetyViolation(f"Wallet {wallet_address!r} is not sanctified")
        ceiling = HillDampener.hill_cap(bid, base_price)
        return min(llm_price, ceiling)

    def validate_x402_payment(
        self,
        wallet_address: str,
        amount: float,
        is_sanctified: bool,
    ) -> None:
        """Validate an autonomous x402 payment: require sanctified wallet and spending cap."""
        if not self.settings:
            logger.error("guard_settings_missing_fail_closed")
            raise SafetyViolation(
                "Cannot validate x402 payment: safety settings not provided."
            )
        if not is_sanctified:
            raise SafetyViolation(
                f"x402 recipient {wallet_address!r} is not sanctified"
            )
        max_payment_config = getattr(self.settings, "max_x402_payment", None)
        if max_payment_config is None:
            logger.warning("max_x402_payment_not_configured", fallback=5.0)
            max_payment = 5.0
        else:
            max_payment = float(max_payment_config)
        if amount > max_payment:
            raise SafetyViolation(
                f"x402 amount {amount} exceeds spending cap {max_payment}"
            )

    def validate_vision(self, vision_result: dict) -> bool:
        """
        Validate VisionSkill output.
        Checks for confidence score and required fields.
        """
        if not vision_result:
            logger.warning("vision_validation_empty")
            raise SafetyViolation("Vision result is empty")

        if "error" in vision_result:
            logger.warning(
                "vision_validation_error_present", error=vision_result["error"]
            )
            raise SafetyViolation(
                f"Vision skill reported error: {vision_result['error']}"
            )

        # Required fields check
        required_fields = ["make", "model", "year", "confidence_score"]
        for field in required_fields:
            if field not in vision_result:
                logger.warning("vision_validation_missing_field", field=field)
                raise SafetyViolation(f"Vision result missing required field: {field}")

        # Confidence threshold check
        confidence = vision_result.get("confidence_score", 0.0)
        if confidence < 0.7:
            logger.warning("vision_validation_low_confidence", confidence=confidence)
            raise SafetyViolation("Vision identification confidence too low")

        return True
