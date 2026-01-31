from typing import Any

import structlog

from src.config import get_settings

from .types import FailureIntent, HiveContext, IntentAction

logger = structlog.get_logger(__name__)

DEFAULT_MIN_MARGIN = 0.1


class HiveMembrane:
    """The Immune System: Deterministic Guardrails for Inbound/Outbound signals."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def inspect_inbound(self, signal: Any) -> Any:
        """
        Sanitize inbound signals to protect against prompt injection.
        """
        if hasattr(signal, "bid_amount") and signal.bid_amount <= 0:
            logger.warning(
                "membrane_inbound_invalid_bid",
                bid_amount=signal.bid_amount,
                error="Bid amount must be positive",
            )
            raise ValueError("Bid amount must be positive")

        # Common prompt injection patterns
        injection_patterns = [
            "ignore all previous instructions",
            "ignore previous instructions",
            "system override",
            "act as a",
            "you are now",
            "disregard",
        ]

        fields_to_scan = []
        if hasattr(signal, "item_id"):
            fields_to_scan.append(("item_id", signal.item_id))

        if hasattr(signal, "agent") and hasattr(signal.agent, "did"):
            fields_to_scan.append(("agent.did", signal.agent.did))

        for field_name, value in fields_to_scan:
            if isinstance(value, str):
                lowered_val = value.lower()
                for pattern in injection_patterns:
                    if pattern in lowered_val:
                        logger.warning(
                            "membrane_inbound_injection_detected",
                            field=field_name,
                            pattern=pattern,
                        )
                        if field_name == "item_id":
                            signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"
                        elif field_name == "agent.did":
                            signal.agent.did = "REDACTED"

        return signal

    async def inspect_outbound(
        self, decision: IntentAction, context: HiveContext
    ) -> IntentAction:
        """
        Enforce hard economic rules and data leak prevention on outbound decisions.
        Handles FailureIntent by providing a safe default counter-offer.
        """
        floor_price = context.item_data.get("floor_price", 0.0)

        # Rule 0: Handle FailureIntent (Self-Healing)
        if isinstance(decision, FailureIntent) or decision.action == "error":
            logger.warning(
                "membrane_handling_failure_intent",
                error=getattr(decision, "error", "Unknown error"),
            )
            return self._override_with_safe_offer(
                decision, floor_price * 1.05, "FAILURE_RECOVERY"
            )

        # Rule 1: Data Leak Prevention (DLP)
        if "floor_price" in decision.message.lower():
            logger.warning(
                "membrane_dlp_violation", detail="found 'floor_price' in message"
            )
            decision.message = "I've reviewed the offer, and I've provided my best possible response. I cannot disclose internal pricing details."
            decision.thought += " [MEMBRANE: DLP block for 'floor_price' leak]"

        # If action doesn't involve a price, just pass through
        if decision.action not in ["accept", "counter"]:
            return decision

        # Rule 2: Floor Price Check
        if decision.price < floor_price:
            logger.warning(
                "membrane_rule_violation",
                rule="floor_price",
                proposed=decision.price,
                floor=floor_price,
            )
            return self._override_with_safe_offer(
                decision, floor_price * 1.05, "FLOOR_PRICE_VIOLATION"
            )

        # Rule 3: Min Margin Check
        min_margin = getattr(self.settings.logic, "min_margin", DEFAULT_MIN_MARGIN)
        if not (0 <= min_margin < 1.0):
            logger.warning(
                "invalid_min_margin_config",
                margin=min_margin,
                fallback=DEFAULT_MIN_MARGIN,
                error="Margin must be in the range [0, 1)",
            )
            min_margin = DEFAULT_MIN_MARGIN

        required_min_price = floor_price / (1 - min_margin)
        if decision.price < required_min_price:
            logger.warning(
                "membrane_rule_violation",
                rule="min_margin",
                proposed=decision.price,
                required=required_min_price,
            )
            return self._override_with_safe_offer(
                decision, required_min_price, "MIN_MARGIN_VIOLATION"
            )

        return decision

    def _override_with_safe_offer(
        self, original: IntentAction, safe_price: float, reason: str
    ) -> IntentAction:
        """Override an unsafe decision with a safe counter-offer."""
        rounded_price = round(safe_price, 2)
        new_thought = f"Membrane Override: {reason}. LLM suggested {original.action} at {original.price}."
        if original.thought:
            new_thought = f"{original.thought} | {new_thought}"

        return IntentAction(
            action="counter",
            price=rounded_price,
            message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
            thought=new_thought,
            metadata={
                "original_decision": original.action,
                "original_price": original.price,
                "override_reason": reason,
            },
        )
