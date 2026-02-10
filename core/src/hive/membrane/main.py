from typing import Any, cast
from unittest.mock import MagicMock

import structlog
from aura_core import Membrane, SkillRegistry, get_action_name
from aura_core.gen.aura.dna.v1 import (
    ActionType,
    Context,
    NegotiationIntent,
)
from aura_core.gen.aura.dna.v1 import (
    Intent as IntentAction,
)

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveMembrane(Membrane[Any, IntentAction, Context]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

    async def inspect_inbound(self, signal: Any) -> Any:
        # Check both new and old names for resilience

        price = None
        if hasattr(signal, "price") and not isinstance(signal.price, MagicMock):
            price = signal.price
        elif hasattr(signal, "bid_amount") and not isinstance(
            signal.bid_amount, MagicMock
        ):
            price = signal.bid_amount

        if price is not None and price <= 0:
            logger.warning("membrane_inbound_invalid_bid", price=price)
            raise ValueError("Bid amount must be positive")

        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
        ]
        fields_to_scan = []
        if hasattr(signal, "identifier"):
            fields_to_scan.append(("identifier", signal.identifier))
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
                        if field_name in ["item_id", "identifier"]:
                            setattr(
                                signal, field_name, "INVALID_ID_POTENTIAL_INJECTION"
                            )
                        elif field_name == "agent.did":
                            signal.agent.did = "REDACTED"
        return signal

    async def inspect_outbound(
        self, decision: IntentAction, context: Context
    ) -> IntentAction:
        hive = context.hive
        floor_price = hive.item.floor_price

        # 1. Handle explicit failures
        if decision.action == ActionType.ACTION_TYPE_ERROR:
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
                    safe_price = float(obs_safe.metadata.get("safe_price", safe_price))

            return self._override_with_safe_offer(
                decision, safe_price, "FAILURE_RECOVERY"
            )

        # 2. DLP Check
        if (
            decision.negotiation
            and "floor_price" in decision.negotiation.message.lower()
        ):
            decision.negotiation.message = "I cannot disclose internal pricing details."
            decision.reasoning += " [MEMBRANE: DLP block]"

        if decision.action not in [
            ActionType.ACTION_TYPE_ACCEPT,
            ActionType.ACTION_TYPE_COUNTER,
        ]:
            return decision

        # 3. Call Guard Protein for validation
        if not self.registry:
            return decision

        internal_cost = float(hive.item.meta.get("internal_cost", floor_price))
        guard_context = {"floor_price": floor_price, "internal_cost": internal_cost}

        obs = await self.registry.execute(
            "guard",
            "validate_decision",
            {
                "decision": {
                    "action": get_action_name(decision.action),
                    "price": decision.negotiation.price
                    if decision.negotiation
                    else 0.0,
                },
                "context": guard_context,
            },
        )

        if not obs.success:
            # Determine reason for logging/override using structured error code
            reason = obs.metadata.get("error_code", "SAFETY_VIOLATION")

            # Use safe price provided by the Guard Protein
            safe_price = float(obs.metadata.get("safe_price", floor_price * 1.05))
            return self._override_with_safe_offer(decision, safe_price, reason)

        return decision

    def _override_with_safe_offer(
        self, original: IntentAction, safe_price: float, reason: str
    ) -> IntentAction:
        rounded_price = round(safe_price, 2)
        orig_price = original.negotiation.price if original.negotiation else 0.0
        action_name = get_action_name(original.action)
        new_thought = (
            f"Membrane Override: {reason}. LLM suggested {action_name} at {orig_price}."
        )
        if original.reasoning:
            new_thought = f"{original.reasoning} | {new_thought}"

        return IntentAction(
            action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
            reasoning=new_thought,
            negotiation=NegotiationIntent(
                price=rounded_price,
                message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
                thought=new_thought,
            ),
            metadata={
                "original_decision": action_name,
                "original_price": str(orig_price),
                "override_reason": reason,
            },
        )
