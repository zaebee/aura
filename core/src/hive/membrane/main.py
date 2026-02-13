from typing import Any

import betterproto
import structlog
from aura_core import HiveContext, IntentAction, Membrane, SkillRegistry
from aura_core.gen.aura.assets import v1 as asset_pb2

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveMembrane(Membrane[Any, IntentAction, HiveContext]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

    async def inspect_inbound(self, signal: Any) -> Any:
        # Normalize bid extraction from Signal proto or legacy object
        bid = 0.0
        try:
            payload_name, payload = betterproto.which_one_of(signal, "payload")
            if payload_name == "negotiation":
                bid = payload.bid_amount
        except Exception:
            bid = getattr(signal, "bid_amount", 0.0)

        if bid < 0:
            raise ValueError("Bid amount must be positive")

        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
        ]

        # Scan fields for injection
        try:
            payload_name, payload = betterproto.which_one_of(signal, "payload")
            if payload_name == "negotiation":
                if any(p in payload.agent.did.lower() for p in injection_patterns):
                    payload.agent.did = "REDACTED"
                    logger.warning("membrane_inbound_injection_detected", field="agent.did")
            elif payload_name == "perception":
                 if any(p in payload.agent.did.lower() for p in injection_patterns):
                    payload.agent.did = "REDACTED"
                    logger.warning("membrane_inbound_injection_detected", field="agent.did")
        except Exception:
            # Fallback for legacy mocks
            did = getattr(getattr(signal, "agent", None), "did", "")
            if any(p in did.lower() for p in injection_patterns):
                signal.agent.did = "REDACTED"
                logger.warning("membrane_inbound_injection_detected", field="agent.did")

        return signal

    async def inspect_outbound(
        self, decision: IntentAction, context: HiveContext
    ) -> IntentAction:

        floor_price = float(context.metadata.get("floor_price", 0.0))
        bid_price = context.hive.offer.bid_amount
        base_price = 0.0

        if context.hive.asset_payload and context.hive.asset_payload.value:
            try:
                asset = asset_pb2.Asset().parse(context.hive.asset_payload.value)
                if asset.rental_terms and asset.rental_terms.price_tiers:
                    base_price = asset.rental_terms.price_tiers[0].price_per_day
            except Exception as e:
                logger.warning("membrane_asset_parse_failed", error=str(e))

        # ActionType is an enum
        from aura_core.gen.aura.core.v1 import ActionType

        # 1. Handle explicit failures
        if decision.action == ActionType.ACTION_TYPE_ERROR:
            safe_price = floor_price * 1.05
            if self.registry:
                obs_safe = await self.registry.execute(
                    "guard",
                    "get_safe_price",
                    {
                        "context": {
                            "floor_price": floor_price,
                            "bid": bid_price,
                            "base_price": base_price
                        },
                        "reason": "FAILURE_RECOVERY",
                    },
                )
                if obs_safe.success:
                    safe_price = float(obs_safe.metadata.get("safe_price", safe_price))

            return self._override_with_safe_offer(
                decision, safe_price, "FAILURE_RECOVERY"
            )

        # 2. DLP Check
        message = decision.negotiation.message if decision.negotiation else ""
        if "floor_price" in message.lower():
            if decision.negotiation:
                decision.negotiation.message = "I cannot disclose internal pricing details."
                decision.negotiation.thought += " [MEMBRANE: DLP block]"

        if decision.action not in [ActionType.ACTION_TYPE_ACCEPT, ActionType.ACTION_TYPE_COUNTER]:
            return decision

        # 3. Call Guard Protein for validation
        if not self.registry:
            return decision

        # Try to get internal cost from metadata or fallback to floor
        internal_cost = float(context.metadata.get("internal_cost", floor_price))
        guard_context = {
            "floor_price": floor_price,
            "internal_cost": internal_cost,
            "bid": bid_price,
            "base_price": base_price
        }

        price = decision.negotiation.price if decision.negotiation else 0.0

        # Guard expects action as string? Engine might need it.
        action_str = decision.action.name.lower().replace("action_type_", "")

        obs = await self.registry.execute(
            "guard",
            "validate_decision",
            {
                "decision": {"action": action_str, "price": price},
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
        from aura_core.gen.aura.core.v1 import ActionType, NegotiationIntent
        rounded_price = round(safe_price, 2)
        orig_price = original.negotiation.price if original.negotiation else 0.0
        orig_thought = original.negotiation.thought if original.negotiation else ""

        new_thought = f"Membrane Override: {reason}. LLM suggested {original.action} at {orig_price}."
        if orig_thought:
            new_thought = f"{orig_thought} | {new_thought}"

        return IntentAction(
            identifier=original.identifier,
            action=ActionType.ACTION_TYPE_COUNTER,
            reasoning=new_thought,
            negotiation=NegotiationIntent(
                price=rounded_price,
                message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
                thought=new_thought,
            ),
            metadata={
                **original.metadata,
                "original_decision": str(original.action),
                "original_price": str(orig_price),
                "override_reason": reason,
            },
        )
