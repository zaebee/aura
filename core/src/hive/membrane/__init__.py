from typing import Any

import structlog
from aura_core import FailureIntent, HiveContext, IntentAction, Membrane

from config import get_settings, settings

logger = structlog.get_logger(__name__)

DEFAULT_MIN_MARGIN = 0.1


class SafetyViolation(Exception):
    """Raised when a negotiation decision violates safety guardrails."""

    pass


class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    """

    def validate_decision(self, decision: dict, context: dict) -> bool:
        action = decision.get("action")
        offered_price = decision.get("price", 0.0)
        floor_price = context.get("floor_price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)

        if offered_price > 0:
            margin = (offered_price - internal_cost) / offered_price
            if margin < settings.safety.min_profit_margin:
                logger.warning(
                    "safety_margin_violation",
                    offered_price=offered_price,
                    internal_cost=internal_cost,
                    margin=margin,
                    min_margin=settings.safety.min_profit_margin,
                )
                raise SafetyViolation("Minimum profit margin violation")
        elif action in ["accept", "counter"]:
            logger.warning("invalid_offered_price", price=offered_price)
            raise SafetyViolation("Invalid offered price")

        if action in ["accept", "counter"] and offered_price < floor_price:
            logger.warning(
                "safety_floor_violation",
                action=action,
                offered_price=offered_price,
                floor_price=floor_price,
            )
            raise SafetyViolation("Floor price violation")
        return True


class HiveMembrane(Membrane[Any, IntentAction, HiveContext]):
    """The Immune System: Deterministic Guardrails for Inbound/Outbound signals."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def inspect_inbound(self, signal: Any) -> Any:
        if hasattr(signal, "bid_amount") and signal.bid_amount <= 0:
            logger.warning("membrane_inbound_invalid_bid", bid_amount=signal.bid_amount)
            raise ValueError("Bid amount must be positive")

        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
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
        floor_price = context.item_data.get("floor_price", 0.0)
        if isinstance(decision, FailureIntent) or decision.action == "error":
            return self._override_with_safe_offer(
                decision, floor_price * 1.05, "FAILURE_RECOVERY"
            )

        if "floor_price" in decision.message.lower():
            decision.message = "I cannot disclose internal pricing details."
            decision.thought += " [MEMBRANE: DLP block]"

        if decision.action not in ["accept", "counter"]:
            return decision
        if decision.price < floor_price:
            return self._override_with_safe_offer(
                decision, floor_price * 1.05, "FLOOR_PRICE_VIOLATION"
            )

        min_margin = getattr(self.settings.logic, "min_margin", DEFAULT_MIN_MARGIN)
        required_min_price = floor_price / (1 - min_margin)
        if decision.price < required_min_price:
            return self._override_with_safe_offer(
                decision, required_min_price, "MIN_MARGIN_VIOLATION"
            )
        return decision

    def _override_with_safe_offer(
        self, original: IntentAction, safe_price: float, reason: str
    ) -> IntentAction:
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
