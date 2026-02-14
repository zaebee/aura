from typing import Any, cast

import structlog
from aura_core import Membrane, SkillRegistry
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    NegotiationIntent,
)

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveMembrane(Membrane[Any, Intent, Context]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

    async def _inspect_transaction_signal(self, signal: Any) -> None:
        """CRISPR Rule pre-check: reject zero-value transaction amounts."""
        amount = getattr(signal, "amount", None)
        if isinstance(amount, int | float) and amount <= 0:
            raise ValueError("Transaction amount must be positive")

    async def inspect_inbound(self, signal: Any) -> Any:
        import betterproto
        from aura_core_gen.aura.core.v1 import Signal

        # Robust extraction for both legacy objects and Protos
        bid_amount = 0.0
        if isinstance(signal, Signal):
            payload_name, payload_value = betterproto.which_one_of(signal, "payload")
            if payload_name == "negotiation" and payload_value:
                bid_amount = getattr(payload_value, "bid_amount", 0.0)
        else:
            bid_amount = getattr(signal, "bid_amount", 0.0)

        if bid_amount < 0:
            logger.warning("membrane_inbound_invalid_bid", bid_amount=bid_amount)
            raise ValueError("Bid amount must be positive")

        await self._inspect_transaction_signal(signal)

        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
        ]
        fields_to_scan = []

        if isinstance(signal, Signal):
            payload_name, payload_value = betterproto.which_one_of(signal, "payload")
            if payload_name == "negotiation" and payload_value:
                fields_to_scan.append(
                    ("item_identifier", getattr(payload_value, "item_identifier", ""))
                )
                agent = getattr(payload_value, "agent", None)
                if agent:
                    fields_to_scan.append(("agent.did", getattr(agent, "did", "")))
            elif payload_name == "perception" and payload_value:
                agent = getattr(payload_value, "agent", None)
                if agent:
                    fields_to_scan.append(("agent.did", getattr(agent, "did", "")))
        else:
            if hasattr(signal, "item_identifier"):
                fields_to_scan.append(("item_identifier", signal.item_identifier))
            elif hasattr(signal, "item_id"):
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
                        if field_name in ["item_id", "item_identifier"]:
                            if isinstance(signal, Signal):
                                payload_name, payload_value = betterproto.which_one_of(
                                    signal, "payload"
                                )
                                if payload_name == "negotiation" and payload_value:
                                    payload_value.item_identifier = (
                                        "INVALID_ID_POTENTIAL_INJECTION"
                                    )
                            else:
                                if hasattr(signal, "item_identifier"):
                                    signal.item_identifier = (
                                        "INVALID_ID_POTENTIAL_INJECTION"
                                    )
                                elif hasattr(signal, "item_id"):
                                    signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"
                        elif field_name == "agent.did":
                            if isinstance(signal, Signal):
                                payload_name, payload_value = betterproto.which_one_of(
                                    signal, "payload"
                                )
                                if (
                                    payload_name in ["negotiation", "perception"]
                                    and payload_value
                                ):
                                    agent = getattr(payload_value, "agent", None)
                                    if agent:
                                        agent.did = "REDACTED"
                            else:
                                signal.agent.did = "REDACTED"
        return signal

    async def inspect_outbound(self, decision: Intent, context: Context) -> Intent:
        ctx_meta = context.metadata.to_dict()
        floor_price = float(str(ctx_meta.get("floor_price", 0.0)))

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
                    safe_price = float(
                        str(obs_safe.metadata.to_dict().get("safe_price", safe_price))
                    )

            return self._override_with_safe_offer(
                decision, safe_price, "FAILURE_RECOVERY"
            )

        # 2. DLP Check
        message = decision.negotiation.message if decision.negotiation else ""
        if "floor_price" in message.lower():
            if decision.negotiation:
                decision.negotiation.message = (
                    "I cannot disclose internal pricing details."
                )
            decision.reasoning += " [MEMBRANE: DLP block]"

        if decision.action not in [
            ActionType.ACTION_TYPE_ACCEPT,
            ActionType.ACTION_TYPE_COUNTER,
        ]:
            return decision

        # 3. Call Guard Protein for validation
        if not self.registry:
            return decision

        internal_cost = float(str(ctx_meta.get("internal_cost", floor_price)))
        guard_context = {"floor_price": floor_price, "internal_cost": internal_cost}

        price = decision.negotiation.price if decision.negotiation else 0.0
        # Map ActionType to strings expected by OutputGuard
        action_map = {
            ActionType.ACTION_TYPE_ACCEPT: "accept",
            ActionType.ACTION_TYPE_COUNTER: "counter",
        }
        action_name = action_map.get(decision.action, str(decision.action.name).lower())

        obs = await self.registry.execute(
            "guard",
            "validate_decision",
            {
                "decision": {"action": action_name, "price": price},
                "context": guard_context,
            },
        )

        if not obs.success:
            # Determine reason for logging/override using structured error code
            reason = "SAFETY_VIOLATION"
            safe_price = floor_price * 1.05
            obs_meta = obs.metadata.to_dict()
            reason = str(obs_meta.get("error_code", "SAFETY_VIOLATION"))
            safe_price = float(str(obs_meta.get("safe_price", safe_price)))

            return self._override_with_safe_offer(decision, safe_price, reason)

        return decision

    def _override_with_safe_offer(
        self, original: Intent, safe_price: float, reason: str
    ) -> Intent:
        rounded_price = round(safe_price, 2)
        orig_price = original.negotiation.price if original.negotiation else 0.0
        new_thought = f"Membrane Override: {reason}. LLM suggested {original.action.name} at {orig_price}."
        if original.reasoning:
            new_thought = f"{original.reasoning} | {new_thought}"

        return Intent(
            action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
            reasoning=new_thought,
            metadata=protobuf.Struct().from_dict(
                {
                    "original_decision": str(original.action.name),
                    "original_price": str(orig_price),
                    "override_reason": str(reason),
                }
            ),
            negotiation=NegotiationIntent(
                price=rounded_price,
                message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
            ),
        )
