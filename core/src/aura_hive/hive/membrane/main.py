from dataclasses import dataclass
from typing import Any, cast

import betterproto
import structlog
from aura_core import Membrane, SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionDerivation,
    DecisionOutcome,
    DecisionReceipt,
    Intent,
    NegotiationIntent,
    RWAVaultIntent,
    TradeIntent,
)
from prometheus_client import REGISTRY, Counter

from aura_hive.config import get_settings

from .receipt import mint, signed, signing_payload

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


@dataclass
class _Verdict:
    """
    The Membrane's finding, accumulated as the outbound path proceeds.

    Kept here rather than written onto the Intent as it goes, because the Intent
    on the override path is replaced part-way and a verdict half-written onto a
    discarded object is how `outcome_gate` nearly lost its first gate.

    First gate wins. A decision that trips DLP and then the floor check records
    DLP_BLOCK, the earlier one: reporting every gate that fired would hand an
    adversary an oracle over the policy configuration — probe with crafted
    offers, read back which invariants answered, and the shape of the hidden
    floor falls out. This constrains only what is recorded; every gate still
    executes.
    """

    outcome: DecisionOutcome = _EMIT
    gate: str = ""
    ruleset_version: str = ""
    derivation: DecisionDerivation | None = None

    def record(self, outcome: DecisionOutcome, gate: str) -> None:
        self.outcome = outcome
        if not self.gate:
            self.gate = gate

    def read_guard_report(self, obs_meta: dict[str, Any]) -> None:
        """
        Take the rule set and the derivation from what the guard reported.

        `or ""` rather than a default, because `str(None)` is "None" — truthy,
        and it would record a sequence of that literal text and a hash claiming
        a derivation that never ran. A Struct round-trips a null value back as
        None, so a key being present is not the same as it carrying one.
        """
        self.ruleset_version = str(obs_meta.get("ruleset_version") or "")
        sequence = str(obs_meta.get("gate_sequence") or "")
        digest = str(obs_meta.get("derivation_hash") or "")
        # Left unset when no declared gate ran — a decision outside the guard's
        # scope, an unwired Membrane, or one of the Membrane's own checks, none
        # of which are declared in a rule set. Recording an empty digest there
        # would assert a derivation that never happened.
        if sequence or digest:
            self.derivation = DecisionDerivation(
                gate_sequence=sequence, derivation_hash=digest
            )


def _mint_for(claim: Intent, emission: Intent, verdict: _Verdict) -> DecisionReceipt:
    """
    `claim` is what the Transformer proposed and `emission` is what is going
    out; they are the same object when the Membrane changed nothing, and the two
    hashes agreeing is then a fact a reader can check rather than an assumption.
    """
    return mint(
        claim=claim,
        emission=emission,
        outcome=verdict.outcome,
        outcome_gate=verdict.gate,
        ruleset_version=verdict.ruleset_version,
        derivation=verdict.derivation,
    )


def _replacing(original: Intent, replacement: Intent) -> Intent:
    """
    Carry forward the fields that name the decision point rather than the decision.

    Three outbound paths return a different Intent instead of editing the one
    they were given — the two refusals and the safe-offer override — and a fresh
    Intent starts blank. It still stands for the same point in the metabolic
    cycle, so identity and trace belong to it as much as to what it replaced.

    The verdict does not travel here any more: it is accumulated in a `_Verdict`
    and minted onto the emission, which is what stopped a decision that tripped
    DLP and was then overridden from reporting the floor as its first gate.

    Nothing reads `Intent.trace` today — the trace that reaches the Observation
    comes from `Context.trace` by way of the Connector. Carrying it is cheap and
    keeps the replacement honest before some later consumer trusts the field.
    """
    replacement.identifier = original.identifier
    replacement.trace = original.trace
    return replacement


def _context_number(ctx_meta: dict[str, Any], key: str, default: float) -> float:
    """
    Read a number out of Context.metadata that may not be one.

    A Struct round-trips a JSON null back as None, and the previous read was
    `float(str(ctx_meta.get(key, default)))` — so a null became `float("None")`
    and a ValueError. Nothing catches it: `MetabolicLoop.execute` wraps neither
    membrane call, so the exception leaves the cycle and the negotiation is lost.

    That is the wrong failure for the component whose job is to be the thing
    that does not let a bad decision out. Refusing safely is its business;
    crashing on its own input is not. An unusable value reads as absent, which
    is what the default already meant.
    """
    value = ctx_meta.get(key, default)
    if value is None:
        return default
    try:
        return float(str(value))
    except (TypeError, ValueError):
        logger.warning("membrane_unusable_context_number", key=key, value=repr(value))
        return default


def _outcome_label(outcome: Any) -> str:
    """`override`, not `2` — the log line is read by people."""
    try:
        name = DecisionOutcome(int(outcome)).name or ""
    except (ValueError, TypeError, AttributeError):
        return f"outcome_{outcome}"
    return name.removeprefix("DECISION_OUTCOME_").lower()


def _action_label(action: Any) -> str:
    """Safely convert ActionType or raw int to a lowercase name string."""
    try:
        name = ActionType(int(action)).name
        return name.lower() if name else f"action_{int(action)}"
    except (ValueError, TypeError, AttributeError):
        return f"action_{action}"


class HiveMembrane(Membrane[Any, Intent, Context]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry

    async def _finish(
        self, claim: Intent, emission: Intent, verdict: _Verdict
    ) -> Intent:
        """
        Attach the receipt to the Intent that will actually be sent, asking
        whoever holds the key to attest it.

        A receipt that cannot be signed is still emitted, unsigned. The decision
        it accompanies has already been made and is already safe by this point,
        so losing it because a key was unreachable would trade the guarantee for
        the attestation — the wrong way round. The version name carries that
        distinction rather than leaving a reader to infer it.
        """
        receipt = _mint_for(claim, emission, verdict)
        emission.receipt = await self._attest(receipt)

        try:
            logger.info(
                "membrane_receipt",
                prefix=emission.receipt.canonical_prefix,
                outcome=_outcome_label(emission.receipt.outcome),
                gate=emission.receipt.outcome_gate or None,
                ruleset=emission.receipt.ruleset_version or None,
                attested=bool(emission.receipt.signature),
            )
        except Exception as e:  # nosec B110
            # The same rule `_record_intervention` follows, and for the same
            # reason: reporting on a decision must never take that decision
            # down. Losing a negotiation over a sentence nobody was going to
            # read at the time is the worst trade in the file.
            logger.error("membrane_receipt_log_failed", error=str(e))

        return emission

    async def _attest(self, receipt: DecisionReceipt) -> DecisionReceipt:
        """Ask the protein that holds the key to sign, or return it unsigned."""
        if not self.registry:
            return receipt

        try:
            # Looked up rather than accessed: settings with no crypto section
            # is a configuration a deployment may legitimately have, and an
            # expected absence should not be discovered by throwing. The try
            # still wraps it, because the promise that nothing here costs the
            # decision should hold from where the code sits rather than from
            # someone having checked each line.
            crypto = getattr(self.settings, "crypto", None)
            chain_id = int(getattr(crypto, "evm_chain_id", 0) or 0)
            obs = await self.registry.execute(
                "transaction",
                "sign_receipt",
                {"payload": signing_payload(receipt, chain_id=chain_id)},
            )
        except Exception as e:
            # Caught for the same reason the metric counter is: an attestation
            # failure must not take down the decision it describes.
            logger.warning("membrane_receipt_unsigned", error=str(e))
            return receipt

        if not obs.success:
            logger.warning("membrane_receipt_unsigned", error=obs.error)
            return receipt

        meta = obs.metadata.to_dict() if obs.metadata is not None else {}
        signer = str(meta.get("signer") or "")
        signature = str(meta.get("signature") or "")
        if not signer or not signature:
            logger.warning("membrane_receipt_unsigned", error="signer reported neither")
            return receipt

        return signed(receipt, signer=signer, signature=signature, chain_id=chain_id)

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
        floor_price = _context_number(ctx_meta, "floor_price", 0.0)

        # Accumulated as the path proceeds and minted once, at whichever return
        # is taken. `decision` is the claim throughout: the only edit before the
        # receipt is built is DLP rewriting prose, which the claim excludes.
        verdict = _Verdict()

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
                verdict.record(_REFUSE, "KYC_FAILURE")
                return await self._finish(
                    decision,
                    _replacing(
                        decision,
                        Intent(
                            action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                            reasoning=decision.reasoning
                            + " [MEMBRANE: KYC compliance failure]",
                            rwa_vault=rwa_intent,
                        ),
                    ),
                    verdict,
                )
            return await self._finish(decision, decision, verdict)

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
                verdict.record(_REFUSE, "HIGH_RISK_TRADE")
                return await self._finish(
                    decision,
                    _replacing(
                        decision,
                        Intent(
                            action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                            reasoning=decision.reasoning
                            + " [MEMBRANE: high-risk trade blocked]",
                            trade=trade_intent,
                        ),
                    ),
                    verdict,
                )
            return await self._finish(decision, decision, verdict)

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

            return await self._override_with_safe_offer(
                decision, safe_price, "FAILURE_RECOVERY", verdict
            )

        # 2. DLP Check
        message = neg_intent.message if neg_intent else ""
        if "floor_price" in message.lower():
            if neg_intent:
                neg_intent.message = "I cannot disclose internal pricing details."
            decision.reasoning += " [MEMBRANE: DLP block]"
            _record_intervention("outbound", "DLP_BLOCK")
            verdict.record(_OVERRIDE, "DLP_BLOCK")

        if decision.action not in [
            ActionType.ACTION_TYPE_ACCEPT,
            ActionType.ACTION_TYPE_COUNTER,
        ]:
            return await self._finish(decision, decision, verdict)

        # 3. Call Guard Protein for validation
        if not self.registry:
            return await self._finish(decision, decision, verdict)

        internal_cost = _context_number(ctx_meta, "internal_cost", floor_price)
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

        # A default-constructed Observation always has an empty Struct here, so
        # this is not the usual betterproto caution — but `metadata=None` is a
        # legal way to build one, and this read moved onto the passing path in
        # the same change that added the derivation. It had only ever run on the
        # failing path before. A crash here would lose the negotiation inside
        # the one component whose job is to never let a bad decision out.
        obs_meta = obs.metadata.to_dict() if obs.metadata is not None else {}

        # Attached to the Intent the guard judged, before any replacement is
        # built, so `_replacing` carries it across the swap like the rest of the
        # fields that describe this decision point.
        verdict.read_guard_report(obs_meta)

        if not obs.success:
            # Determine reason for logging/override using structured error code
            safe_price = floor_price * 1.05
            reason = str(obs_meta.get("error_code", "SAFETY_VIOLATION"))
            safe_price = float(str(obs_meta.get("safe_price", safe_price)))

            return await self._override_with_safe_offer(
                decision, safe_price, reason, verdict
            )

        return await self._finish(decision, decision, verdict)

    async def _override_with_safe_offer(
        self, original: Intent, safe_price: float, reason: str, verdict: _Verdict
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
        verdict.record(_OVERRIDE, reason)
        return await self._finish(original, _replacing(original, replacement), verdict)
