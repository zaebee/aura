from typing import Any

import structlog
from aura_core import FailureIntent, HiveContext, IntentAction, Membrane, SkillRegistry

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveMembrane(Membrane[Any, IntentAction, HiveContext]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

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

        # 1. Handle explicit failures
        if isinstance(decision, FailureIntent) or decision.action == "error":
            safe_price = floor_price * 1.05
            if self.registry:
                obs_safe = await self.registry.execute(
                    "guard",
                    "get_safe_price",
                    {
                        "context": {"floor_price": floor_price},
                        "reason": "FAILURE_RECOVERY",
                    },
                )
                if obs_safe.success:
                    safe_price = obs_safe.data["safe_price"]

            return self._override_with_safe_offer(
                decision, safe_price, "FAILURE_RECOVERY"
            )

        # 2. DLP Check
        if "floor_price" in decision.message.lower():
            decision.message = "I cannot disclose internal pricing details."
            decision.thought += " [MEMBRANE: DLP block]"

        if decision.action not in ["accept", "counter"]:
            return decision

        # 3. Call Guard Protein for validation
        if not self.registry:
            return decision

        internal_cost = context.item_data.get("meta", {}).get(
            "internal_cost", floor_price
        )
        guard_context = {"floor_price": floor_price, "internal_cost": internal_cost}

        obs = await self.registry.execute(
            "guard",
            "validate_decision",
            {
                "decision": {"action": decision.action, "price": decision.price},
                "context": guard_context,
            },
        )

        if not obs.success:
            # Determine reason for logging/override using structured error code
            reason = obs.data.get("error_code", "SAFETY_VIOLATION")

            # Use safe price provided by the Guard Protein
            safe_price = obs.data.get("safe_price", floor_price * 1.05)
            return self._override_with_safe_offer(decision, safe_price, reason)

        return decision

    def _override_with_safe_offer(
        self, original: IntentAction, safe_price: float, reason: str
    ) -> IntentAction:
        rounded_price = round(safe_price, 2)
        new_thought = f"Membrane Override: {reason}. LLM suggested {original.action} at {getattr(original, 'price', 0.0)}."
        if original.thought:
            new_thought = f"{original.thought} | {new_thought}"

        return IntentAction(
            action="counter",
            price=rounded_price,
            message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
            thought=new_thought,
            metadata={
                "original_decision": original.action,
                "original_price": getattr(original, "price", 0.0),
                "override_reason": reason,
            },
        )
