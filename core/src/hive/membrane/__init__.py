from typing import Any

import structlog
from aura_core import FailureIntent, HiveContext, IntentAction, Membrane, SkillRegistry

from config import get_settings

logger = structlog.get_logger(__name__)

# Re-exporting from Guard Protein for backward compatibility
from hive.proteins.guard import GuardProtein, SafetyViolation
from hive.proteins.guard._output_guard import OutputGuard

class HiveMembrane(Membrane[Any, IntentAction, HiveContext]):
    """The Immune System: Deterministic Guardrails via Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry or SkillRegistry()

    async def inspect_inbound(self, signal: Any) -> Any:
        # Sacred Rule: Positive bid amounts only
        if hasattr(signal, "bid_amount") and signal.bid_amount <= 0:
             raise ValueError("Bid amount must be positive")

        guard = self.registry.get("guard")
        if guard:
            obs = await guard.execute("sanitize_input", {"signal": signal})
            if obs.success:
                return obs.data

        # Legacy fallback logic for tests if guard protein not present
        injection_patterns = ["ignore all previous instructions", "system override", "you are now"]
        if hasattr(signal, "item_id") and isinstance(signal.item_id, str):
            for p in injection_patterns:
                if p in signal.item_id.lower():
                    signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"

        if hasattr(signal, "agent") and hasattr(signal.agent, "did") and isinstance(signal.agent.did, str):
            for p in injection_patterns:
                if p in signal.agent.did.lower():
                    signal.agent.did = "REDACTED"

        return signal

    async def inspect_outbound(
        self, decision: IntentAction, context: HiveContext
    ) -> IntentAction:
        floor_price = context.item_data.get("floor_price", 0.0)

        # Redact floor price mentions (Sacred Rule)
        if "floor_price" in decision.message.lower():
            decision.message = "I cannot disclose internal pricing details."
            decision.thought += " [MEMBRANE: DLP block]"

        guard = self.registry.get("guard")
        if not guard:
            # Legacy fallback for tests
            if decision.action in ["accept", "counter"] and decision.price < floor_price:
                 return self._override_with_safe_offer(decision, floor_price * 1.05, "FLOOR_PRICE_VIOLATION")

            min_margin = getattr(self.settings.logic, "min_margin", 0.1)
            required_min_price = floor_price / (1 - min_margin)
            if decision.action in ["accept", "counter"] and decision.price < required_min_price:
                return self._override_with_safe_offer(decision, required_min_price, "MIN_MARGIN_VIOLATION")

            return decision

        obs = await guard.execute("validate_decision", {
            "decision": {
                "action": decision.action,
                "price": decision.price
            },
            "context": {
                "floor_price": floor_price
            }
        })

        if not obs.success:
            reason = obs.error or "UNKNOWN_VIOLATION"
            safe_price = obs.data.get("safe_price", floor_price * 1.05)
            return self._override_with_safe_offer(decision, safe_price, reason)

        return decision

    def _override_with_safe_offer(
        self, original: IntentAction, safe_price: float, reason: str
    ) -> IntentAction:
        rounded_price = round(safe_price, 2)
        new_thought = f"<think>\nMembrane Override: {reason}. LLM suggested {original.action} at {original.price}.\n</think>"
        if original.thought:
            new_thought = f"{original.thought}\n{new_thought}"

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
