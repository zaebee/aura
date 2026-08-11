from typing import Any, cast

import betterproto
import structlog
from aura_core import Membrane, SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    Intent,
    NegotiationIntent,
    RWAVaultIntent,
    TradeIntent,
)
from prometheus_client import REGISTRY, Counter

from aura_hive.config import get_settings

logger = structlog.get_logger(__name__)


def _get_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    """
    Idempotent registration: the default REGISTRY raises on a duplicate name,
    and tests import this module more than once.

    Defined here rather than imported from the telemetry protein: the Membrane
    is a nucleus organ and proteins sit a level below it. Four lines of
    duplication beat an upward dependency.
    """
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        # Same name, different labels is a mistake that would otherwise surface
        # far from its cause — as a ValueError inside .labels() at the first
        # intervention. Raise where the mismatch was introduced.
        registered = getattr(existing, "_labelnames", None)
        if registered is not None and tuple(registered) != tuple(labelnames):
            raise ValueError(
                f"collector {name!r} is already registered with labels "
                f"{tuple(registered)!r}, not {tuple(labelnames)!r}"
            )
        return cast(Counter, existing)
    return Counter(name, documentation, labelnames)


# Every time the guard changed or refused what the Transformer produced. This is
# the rate to watch: it measures how often free reasoning lands somewhere the
# guarantee has to catch, which is the only number that says whether the
# membrane is earning its place.
membrane_interventions_total = _get_counter(
    "membrane_interventions_total",
    "Decisions the Membrane altered, sanitised or rejected",
    ["direction", "reason"],
)


def _record_intervention(direction: str, reason: str, **fields: Any) -> None:
    """Count it and say so. An intervention that leaves no trace cannot be measured."""
    try:
        membrane_interventions_total.labels(direction=direction, reason=reason).inc()
        # Inside the try as well: **fields is caller-supplied and could fail to
        # serialise, and a crash while reporting an intervention is the same
        # failure as a crash while counting one.
        logger.warning(
            "membrane_intervention", direction=direction, reason=reason, **fields
        )
    except Exception as e:
        # Accounting must never take the guarantee down with it. The decision
        # this call accompanies has already been made and still stands; losing a
        # count degrades observability, raising here would lose the negotiation.
        logger.error(
            "membrane_metric_failed", direction=direction, reason=reason, error=str(e)
        )


# betterproto enums subclass int, so mypy reads a bare member access as `int`
# (the same reason ActionType is cast at every use below). Casting once here
# beats repeating it at each call site.
_EMIT = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_EMIT)
_OVERRIDE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_OVERRIDE)
_REFUSE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_REFUSE)


def _stamp(decision: Intent, outcome: DecisionOutcome, gate: str) -> Intent:
    """
    Record what the Membrane did, on the Intent that will actually be sent.

    First gate wins. A decision that trips DLP and then the floor check records
    DLP_BLOCK, the earlier one: reporting every gate that fired would hand an
    adversary an oracle over the policy configuration — probe with crafted
    offers, read back which invariants answered, and the shape of the hidden
    floor falls out.

    This constrains only what is *recorded*. Every gate still executes;
    short-circuiting the floor check to keep the label tidy would trade a
    guarantee for a string.
    """
    decision.outcome = outcome
    if not decision.outcome_gate:
        decision.outcome_gate = gate
    return decision


def _settle(decision: Intent) -> Intent:
    """
    Nothing further fired, so the Membrane emitted what it was given.

    EMIT is claimed only when no earlier gate has already stamped this Intent —
    a message sanitised by DLP is still an override even though the price that
    follows it passes the guard untouched.
    """
    if not decision.outcome_gate:
        decision.outcome = _EMIT
    return decision


def _action_label(action: Any) -> str:
    """Safely convert ActionType or raw int to a lowercase name string."""
    try:
        name = ActionType(int(action)).name
        return name.lower() if name else f"action_{int(action)}"
    except (ValueError, AttributeError):
        return f"action_{int(action)}"


class HiveMembrane(Membrane[Any, Intent, Context]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

    async def inspect_inbound(self, signal: Any) -> Any:
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
            _record_intervention("inbound", "INVALID_BID", bid_amount=bid_amount)
            raise ValueError("Bid amount must be positive")

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
                        _record_intervention(
                            "inbound",
                            "PROMPT_INJECTION",
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

        params_name, params_value = betterproto.which_one_of(decision, "params")

        # RWA vault guard: backstop for KYC failures that slipped through
        if params_name == "rwa_vault" and params_value is not None:
            rwa_intent = cast(RWAVaultIntent, params_value)
            if not rwa_intent.compliance.kyc_passed:
                _record_intervention(
                    "outbound",
                    "KYC_FAILURE",
                    violation_code=rwa_intent.compliance.violation_code,
                    wallet_address=rwa_intent.wallet_address,
                )
                return _stamp(
                    Intent(
                        action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                        reasoning=decision.reasoning
                        + " [MEMBRANE: KYC compliance failure]",
                        rwa_vault=rwa_intent,
                    ),
                    _REFUSE,
                    "KYC_FAILURE",
                )
            return _settle(decision)

        # Trade intent guard: backstop for high-risk trades that slipped through
        if params_name == "trade" and params_value is not None:
            trade_intent = cast(TradeIntent, params_value)
            risk_score = trade_intent.validation_score.risk_score
            risk_threshold = getattr(self.settings.safety, "trade_risk_threshold", 0.10)
            if risk_score > risk_threshold:
                _record_intervention(
                    "outbound",
                    "HIGH_RISK_TRADE",
                    risk_score=risk_score,
                    risk_category=trade_intent.validation_score.risk_category,
                )
                return _stamp(
                    Intent(
                        action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                        reasoning=decision.reasoning
                        + " [MEMBRANE: high-risk trade blocked]",
                        trade=trade_intent,
                    ),
                    _REFUSE,
                    "HIGH_RISK_TRADE",
                )
            return _settle(decision)

        neg_intent = params_value if params_name == "negotiation" else None

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
        message = neg_intent.message if neg_intent else ""
        if "floor_price" in message.lower():
            if neg_intent:
                neg_intent.message = "I cannot disclose internal pricing details."
            decision.reasoning += " [MEMBRANE: DLP block]"
            _record_intervention("outbound", "DLP_BLOCK")
            _stamp(decision, _OVERRIDE, "DLP_BLOCK")

        if decision.action not in [
            ActionType.ACTION_TYPE_ACCEPT,
            ActionType.ACTION_TYPE_COUNTER,
        ]:
            return _settle(decision)

        # 3. Call Guard Protein for validation
        if not self.registry:
            return _settle(decision)

        internal_cost = float(str(ctx_meta.get("internal_cost", floor_price)))
        guard_context = {"floor_price": floor_price, "internal_cost": internal_cost}

        price = neg_intent.price if neg_intent else 0.0
        # Map ActionType to strings expected by OutputGuard
        action_map = {
            ActionType.ACTION_TYPE_ACCEPT: "accept",
            ActionType.ACTION_TYPE_COUNTER: "counter",
        }
        action_name = action_map.get(decision.action, _action_label(decision.action))

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

        return _settle(decision)

    def _override_with_safe_offer(
        self, original: Intent, safe_price: float, reason: str
    ) -> Intent:
        _record_intervention("outbound", reason, safe_price=round(safe_price, 2))
        rounded_price = round(safe_price, 2)
        params_name, params_value = betterproto.which_one_of(original, "params")
        neg_intent = params_value if params_name == "negotiation" else None
        orig_price = neg_intent.price if neg_intent else 0.0
        new_thought = f"Membrane Override: {reason}. LLM suggested {_action_label(original.action)} at {orig_price}."
        if original.reasoning:
            new_thought = f"{original.reasoning} | {new_thought}"

        replacement = Intent(
            action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
            reasoning=new_thought,
            metadata=make_struct(
                {
                    "original_decision": _action_label(original.action),
                    "original_price": str(orig_price),
                    "override_reason": str(reason),
                }
            ),
            negotiation=NegotiationIntent(
                price=rounded_price,
                message=f"I've reached my final limit for this item. My best offer is ${rounded_price:.2f}.",
            ),
        )
        # This is a fresh Intent, so an earlier gate's mark does not come along
        # with it. Carry it forward before stamping, or a decision that tripped
        # DLP and then the floor check would report the floor as the first gate.
        replacement.outcome_gate = original.outcome_gate
        return _stamp(replacement, _OVERRIDE, str(reason))
