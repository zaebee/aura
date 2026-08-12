from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    Membrane,
    SkillRegistry,
    make_struct,
)
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
_UNAVAILABLE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE)


@dataclass
class _Verdict:
    """
    The Membrane's finding, accumulated as the outbound path proceeds.

    Kept here rather than written onto the Intent as it goes, because the Intent
    on the override path is replaced part-way and a verdict half-written onto a
    discarded object is how `outcome_gate` nearly lost its first gate.

    **`gate` and `override_scope` answer different questions, so they
    accumulate by different rules.**

    `gate` answers "which rule explains this outcome". First gate wins *within
    an outcome class*, and resets when the class changes. Within a class the
    earlier gate is the one that explains the finding — a decision that trips
    DLP and then the floor check is reported as DLP_BLOCK — and holding to the
    first also keeps the schema stable and leaves the full detail to
    `gate_sequence`, which the auditor has. But first-wins *forever* was a bug:
    DLP → substitution → post-condition failure shipped
    `outcome=UNAVAILABLE, outcome_gate=DLP_BLOCK`, a receipt saying "unavailable
    because DLP" to the one party this document is written for, and one the
    error table contradicts (a psi failure is POSTCONDITION_VIOLATION) while
    `verify()` checks no gate/outcome coherence for UNAVAILABLE and so ships it
    silently. The gate that explained the previous class cannot explain the new
    one, so it is discarded with it.

    An earlier version of this docstring justified first-wins as denying an
    adversary an oracle over the policy configuration. That reasoning is a
    fossil: since the gateway trim the counterparty never sees `outcome_gate`
    at all. Schema stability and `gate_sequence` are the reasons that survive.

    `override_scope` answers "did the decidable content change", so it is
    **monotonic toward "value"** and does not ride `gate` at all. It starts
    empty, a prose-only intervention raises it to "prose", and a price
    substitution sets "value" unconditionally. Pairing it with the winning gate
    was the previous fix and it produced the branch's central contradiction: a
    DLP block followed by a price substitution reported `scope="prose"` while
    the digests differed, and `verify()` — which checks scope against the
    emission delta — failed a receipt the Membrane had just minted. Every
    intervention has to reach this field, because the question it answers is
    about all of them together, not about whichever one is named.

    It stays a property recomputed from `self.outcome` rather than a stored
    value some call site is trusted to clear, so a decision that moves past
    OVERRIDE can never leave a scope behind — there is no field to forget.
    """

    outcome: DecisionOutcome = _EMIT
    gate: str = ""
    ruleset_version: str = ""
    derivation: DecisionDerivation | None = None
    _scope: str = field(default="", repr=False)

    def record(self, outcome: DecisionOutcome, gate: str, scope: str = "") -> None:
        # Checked on EVERY OVERRIDE call, not only the one that establishes the
        # gate. Now that scope is monotonic, the second OVERRIDE record is
        # load-bearing on its own: it is what raises a DLP-then-substitution
        # decision from "prose" to "value". A call site that forgot its scope
        # there used to slip through this guard entirely and ship the receipt
        # `verify()` rejects.
        if outcome == _OVERRIDE and not scope:
            raise ValueError(
                f"gate {gate!r} recorded outcome OVERRIDE with no scope; "
                "every OVERRIDE call site must pass 'prose' or 'value'"
            )

        if outcome != self.outcome:
            # The class changed, so the gate that explained the old outcome is
            # not an explanation of this one. Replace it rather than keep it.
            self.gate = gate
        elif not self.gate:
            self.gate = gate

        self.outcome = outcome

        # Monotonic: value is absorbing, prose only fills an empty scope. Order
        # of interventions must not change the answer to "did the decidable
        # content change".
        if scope == "value":
            self._scope = "value"
        elif scope == "prose" and self._scope != "value":
            self._scope = "prose"

    @property
    def override_scope(self) -> str:
        """
        Whether this decision's interventions reached the decidable content,
        or "" when the final outcome is not OVERRIDE.

        Derived from `self.outcome` on every read instead of stored plainly,
        so it cannot outlive the OVERRIDE outcome that justified it — see the
        class docstring for the failure this closes.
        """
        return self._scope if self.outcome == _OVERRIDE else ""

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


def _mint_for(
    claim: Intent, emission: Intent, verdict: _Verdict, request_id: str
) -> DecisionReceipt:
    """
    `claim` is what the Transformer proposed and `emission` is what is going
    out; they are the same object when the Membrane changed nothing, and the two
    hashes agreeing is then a fact a reader can check rather than an assumption.

    `decision_id` is the emission's identifier rather than the claim's: on the
    override path the emission is a replacement Intent, and `_replacing` carries
    the identifier across from the original, so this still names the one
    decision the receipt describes. `request_id` names the negotiation session
    it belongs to, and comes from the Context the outbound path was given —
    nothing on the Intent carries it.
    """
    return mint(
        claim=claim,
        emission=emission,
        outcome=verdict.outcome,
        outcome_gate=verdict.gate,
        ruleset_version=verdict.ruleset_version,
        derivation=verdict.derivation,
        issued_at=datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        decision_id=emission.identifier,
        request_id=request_id,
        override_scope=verdict.override_scope,
    )


def _as_dict(struct: Any) -> dict[str, Any]:
    """A protobuf Struct as a plain dict, tolerating one that is not there."""
    return struct.to_dict() if struct is not None else {}


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
    replacement.steps = original.steps

    # Merged rather than copied, and the replacement wins on a conflict:
    # `_override_with_safe_offer` records what it replaced, and carrying the
    # original's metadata must not bury that. Keys the replacement did not set
    # survive, which is the whole point — a hand-written replacement drops them
    # silently, since the constructor is happy to default them and nothing warns.
    # Read defensively. The paths that build replacements omit metadata rather
    # than passing None, and betterproto default-constructs the field on access,
    # so neither read can raise today. But this helper is the one place four
    # paths funnel through, and it exists precisely because hand-built
    # replacements lose what nobody remembered — it should not be the thing that
    # raises on a caller who built one badly.
    merged = {**_as_dict(original.metadata), **_as_dict(replacement.metadata)}
    if merged:
        replacement.metadata = make_struct(merged)

    return replacement


def _rejection() -> Intent:
    """
    What leaves when the post-condition did not hold.

    Deliberately carries no price and no reason the counterparty can read: the
    decision was stopped because we could not establish our own guarantee, and
    saying which clause failed would describe the policy boundary to the party
    the policy exists to hold at arm's length.
    """
    return Intent(
        action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
        reasoning="Membrane: post-condition not established",
    )


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


def _neutral_price_message(action: Any, price: float) -> str:
    """
    State the price without stating that a guard produced it.

    Phrased from the action rather than fixed, because the DLP block keeps the
    model's action: sanitising an ACCEPT used to emit "My counter-offer for this
    item is $X", which contradicts the `accepted` result the counterparty
    receives alongside it. A message that disagrees with the decision beside it
    is its own tell.
    """
    if action == ActionType.ACTION_TYPE_ACCEPT:
        return f"I accept your offer at ${price:.2f}."
    return f"My counter-offer for this item is ${price:.2f}."


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
        self, claim: Intent, emission: Intent, verdict: _Verdict, request_id: str
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
        receipt = _mint_for(claim, emission, verdict, request_id)
        emission.receipt = await self._attest(receipt)

        try:
            logger.info(
                "membrane_receipt",
                prefix=emission.receipt.canonical_prefix,
                receipt=emission.receipt.to_dict(),
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

    async def _postcondition_holds(
        self, price: float, guard_context: dict[str, Any], verdict: _Verdict
    ) -> bool:
        """
        Whether the value about to be sent satisfies what the rule set promises.

        Fails closed on every path that is not an explicit pass, including a
        guard that could not be reached: a post-condition nobody evaluated has
        not been established, and this is the last checkpoint before the wire.

        Deliberately no `if not self.registry: return True` early exit. An
        unwired Membrane is exactly the unreachable-guard case this fails
        closed on, not an exemption from it — the fallback that motivated this
        method (`floor_price * 1.05` at the two `_override_with_safe_offer`
        call sites) is reached precisely when the guard could not be asked, and
        letting an unjudged price through there is the bug this closes.
        """
        if self.registry is None:
            logger.error("membrane_postcondition_unreachable", error="no guard wired")
            verdict.record(_UNAVAILABLE, "POSTCONDITION_VIOLATION")
            return False

        try:
            obs = await self.registry.execute(
                "guard",
                "check_postcondition",
                {"emission": {"price": price}, "context": guard_context},
            )
        except Exception as exc:
            logger.error("membrane_postcondition_unreachable", error=str(exc))
            verdict.record(_UNAVAILABLE, "POSTCONDITION_VIOLATION")
            return False

        meta = obs.metadata.to_dict() if obs.metadata is not None else {}
        if obs.success and bool(meta.get("holds")):
            return True

        logger.error(
            "membrane_postcondition_violated",
            clause=str(meta.get("failed_clause") or ""),
            price=price,
        )
        verdict.record(_UNAVAILABLE, "POSTCONDITION_VIOLATION")
        return False

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
        """
        Judge the Transformer's decision and return the one to send.

        **No decision the Intent carries is modified in place.** Every path that
        changes one — the two refusals, the safe-offer override, the DLP
        sanitisation — builds a replacement and leaves the caller's object
        alone.

        The one exception is `currency_code`, stamped onto the caller's
        `NegotiationIntent` from the Context below. That is normalisation, not a
        decision: the denomination is a property of the request and the model
        never had a say in it. It is written before `claim` and the emission can
        diverge, deliberately, so both digests cover the same denomination
        rather than differing over a field nothing decided. The consequence is
        worth stating plainly and `DECISION_RECEIPT.md` §3.2 now does: what
        `claim_hash` digests is the proposal **as normalised by the Membrane**,
        not the byte-exact object the Transformer handed over.

        That is not tidiness. The receipt reports what the Membrane did by
        comparing a digest of what was proposed against a digest of what is
        going out, and one object cannot produce two: editing the proposal into
        the emission leaves both hashes taken after the change, and a receipt
        that reports no intervention. The evidence lives in the difference
        between two objects, so there have to be two.

        `inspect_inbound` deliberately does the opposite and redacts the Signal
        in place. Nothing attests to an inbound signal, so there is no earlier
        state anything needs to compare against; the asymmetry follows from what
        each boundary is for rather than from inconsistency.
        """
        ctx_meta = context.metadata.to_dict()
        floor_price = _context_number(ctx_meta, "floor_price", 0.0)

        # The session id the substitute price's jitter is keyed on. Read via
        # `which_one_of` rather than `context.hive` — `Context.data` is a
        # oneof, and a message field is never `None` on betterproto, so an
        # identity check on the field would always be true and this would
        # read a default-constructed HiveContextData instead of "absent".
        hive = betterproto.which_one_of(context, "data")[1]
        request_id = getattr(hive, "request_id", "") if hive else ""

        # Accumulated as the path proceeds and minted once, at whichever return
        # is taken.
        verdict = _Verdict()

        # What the Transformer proposed, kept intact for the receipt. Rebound
        # only if a later step needs to work on a replacement; `decision` is
        # then the thing being sent and this is the thing that was asked for.
        claim = decision

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
                    claim,
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
                    request_id,
                )
            return await self._finish(claim, decision, verdict, request_id)

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
                    claim,
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
                    request_id,
                )
            return await self._finish(claim, decision, verdict, request_id)

        neg_intent = params_value if params_name == "negotiation" else None

        # From context, not from the model. Stamped as soon as neg_intent is
        # resolved and before `claim` and `decision` can diverge — the DLP
        # block below is the only place that happens in this path, and it
        # copies `currency_code` forward from this same object — so both the
        # claim and the emission carry it and the two digests stay comparable.
        if neg_intent is not None and hive is not None:
            neg_intent.currency_code = hive.offer.currency_code

        # 1. Handle explicit failures
        if decision.action == ActionType.ACTION_TYPE_ERROR:
            # Same default as the guard block below: an unspecified cost reads
            # as the floor rather than as free, so a context that never
            # supplied one does not vacuously satisfy the margin clause.
            internal_cost = _context_number(ctx_meta, "internal_cost", floor_price)
            guard_context = {
                "floor_price": floor_price,
                "internal_cost": internal_cost,
                "request_id": request_id,
            }

            safe_price = floor_price * 1.05
            if self.registry:
                obs_safe = await self.registry.execute(
                    "guard",
                    "get_safe_price",
                    {
                        # The SAME context psi is checked against, floor and
                        # cost together. Asking for a substitute priced from
                        # the floor alone and then judging it against the cost
                        # starves this path wherever cost > floor x (1 - m):
                        # floor 1000, cost 1200, m 0.1 yielded 1111.11,
                        # PSI_MIN_MARGIN refused it, and the recovery that
                        # exists to keep a broken decision alive emitted
                        # nothing. Pre-branch it emitted an unsafe price
                        # instead; neither is the substitute the guard can
                        # actually compute from these premises.
                        "context": guard_context,
                        "reason": "FAILURE_RECOVERY",
                        "request_id": request_id,
                    },
                )
                if obs_safe.success:
                    safe_price = float(
                        str(obs_safe.metadata.to_dict().get("safe_price", safe_price))
                    )

            return await self._override_with_safe_offer(
                decision,
                safe_price,
                "FAILURE_RECOVERY",
                verdict,
                guard_context,
                request_id,
                claim,
            )

        # 2. DLP Check
        message = neg_intent.message if neg_intent else ""
        if "floor_price" in message.lower():
            _record_intervention("outbound", "DLP_BLOCK")
            # The substitution here touches only the message — the sanitised
            # negotiation keeps the same price and item — so claim and emission
            # hash alike. "prose" says why: a reader who sees the two hashes
            # agree under an OVERRIDE outcome can tell "prose changed, value
            # did not" from "this receipt claims a substitution that left no
            # trace" without knowing which gate names are prose-only.
            #
            # It raises the scope only from empty. If the guard later
            # substitutes a price on this same decision, that call sets "value"
            # over it — the digests will differ, and the receipt has to say so.
            verdict.record(_OVERRIDE, "DLP_BLOCK", "prose")
            # Sanitised into a replacement rather than written back over the
            # caller's Intent. The receipt reports what the Membrane did by
            # comparing a digest of the proposal against a digest of what was
            # sent, and one object cannot produce two — editing in place would
            # leave nothing to compare against further down this path.
            sanitised = _replacing(
                decision,
                Intent(
                    action=decision.action,
                    reasoning=decision.reasoning + " [MEMBRANE: DLP block]",
                    negotiation=NegotiationIntent(
                        item_identifier=neg_intent.item_identifier,
                        item_domain=neg_intent.item_domain,
                        price=neg_intent.price,
                        # Neutral rather than "I cannot disclose internal
                        # pricing details.": that line told the counterparty
                        # a DLP rule had fired, which is exactly the kind of
                        # tell this exists to remove. See the override
                        # message below for the fuller rationale — the two
                        # are the same fix applied at two emission points.
                        # Phrased from the action, because this path keeps the
                        # model's: an ACCEPT sanitised into a "counter-offer"
                        # contradicts the result sent beside it.
                        message=_neutral_price_message(
                            decision.action, neg_intent.price
                        ),
                        thought=neg_intent.thought,
                        # Carried forward like the other decidable fields. Left
                        # out, the sanitised copy would default to an empty
                        # currency while `claim` (the object stamped above)
                        # keeps the real one — a currency-only mismatch that
                        # would make a prose-only DLP block look like a value
                        # override under `verify`.
                        currency_code=neg_intent.currency_code,
                    ),
                )
                if neg_intent
                else Intent(
                    action=decision.action,
                    reasoning=decision.reasoning + " [MEMBRANE: DLP block]",
                ),
            )
            # `claim` stays the Intent the Transformer produced; everything
            # downstream now works on the sanitised copy.
            claim, decision = decision, sanitised
            neg_intent = (
                betterproto.which_one_of(decision, "params")[1] if neg_intent else None
            )

        if decision.action not in [
            ActionType.ACTION_TYPE_ACCEPT,
            ActionType.ACTION_TYPE_COUNTER,
        ]:
            return await self._finish(claim, decision, verdict, request_id)

        internal_cost = _context_number(ctx_meta, "internal_cost", floor_price)
        guard_context = {
            "floor_price": floor_price,
            "internal_cost": internal_cost,
            "request_id": request_id,
        }

        price = neg_intent.price if neg_intent else 0.0

        # 3. Call Guard Protein for validation
        #
        # An unwired registry skips the gates — there is nothing to ask — but
        # NOT the post-condition. It used to return here, four screens below a
        # `_postcondition_holds` docstring stating that an unwired Membrane "is
        # exactly the unreachable-guard case this fails closed on, not an
        # exemption from it". The early return made that false: with no registry
        # a price of 1.0 against a floor of 1000 was emitted, EMIT, and the
        # receipt verified. The one branch the whole method exists to close was
        # reachable by never wiring the thing that closes it. `_postcondition_
        # holds` records UNAVAILABLE and refuses on its own, so falling through
        # to it is all that is needed.
        if self.registry:
            # Map ActionType to strings expected by OutputGuard
            action_map = {
                ActionType.ACTION_TYPE_ACCEPT: "accept",
                ActionType.ACTION_TYPE_COUNTER: "counter",
            }
            action_name = action_map.get(
                decision.action, _action_label(decision.action)
            )

            obs = await self.registry.execute(
                "guard",
                "validate_decision",
                {
                    "decision": {"action": action_name, "price": price},
                    "context": guard_context,
                },
            )

            # A default-constructed Observation always has an empty Struct here,
            # so this is not the usual betterproto caution — but `metadata=None`
            # is a legal way to build one, and this read moved onto the passing
            # path in the same change that added the derivation. It had only ever
            # run on the failing path before. A crash here would lose the
            # negotiation inside the one component whose job is to never let a
            # bad decision out.
            obs_meta = obs.metadata.to_dict() if obs.metadata is not None else {}

            # Attached to the Intent the guard judged, before any replacement is
            # built, so `_replacing` carries it across the swap like the rest of
            # the fields that describe this decision point.
            verdict.read_guard_report(obs_meta)

            if not obs.success:
                # Determine reason for logging/override using structured error code
                safe_price = floor_price * 1.05
                reason = str(obs_meta.get("error_code", "SAFETY_VIOLATION"))
                safe_price = float(str(obs_meta.get("safe_price", safe_price)))

                return await self._override_with_safe_offer(
                    decision,
                    safe_price,
                    reason,
                    verdict,
                    guard_context,
                    request_id,
                    claim,
                )

        if not await self._postcondition_holds(price, guard_context, verdict):
            # Counted like every other refusal. A psi failure on this path is
            # the Membrane rejecting the model's own price, and it used to be
            # the one intervention that left no trace in the counter.
            _record_intervention("outbound", "POSTCONDITION_VIOLATION", price=price)
            return await self._finish(
                claim, _replacing(decision, _rejection()), verdict, request_id
            )

        return await self._finish(claim, decision, verdict, request_id)

    async def _override_with_safe_offer(
        self,
        original: Intent,
        safe_price: float,
        reason: str,
        verdict: _Verdict,
        guard_context: dict[str, Any],
        request_id: str,
        claim: Intent | None = None,
    ) -> Intent:
        rounded_price = round(safe_price, 2)

        # Counted AFTER the post-condition, and under the reason that actually
        # describes the outcome. Counting `reason` first meant every decision
        # that went on to fail psi was tallied as a completed substitution under
        # the gate that proposed it, so the intervention rate — the one number
        # that says whether the Membrane is earning its place — included
        # decisions that emitted nothing at all.
        if not await self._postcondition_holds(rounded_price, guard_context, verdict):
            _record_intervention(
                "outbound", "POSTCONDITION_VIOLATION", attempted_reason=reason
            )
            return await self._finish(
                claim or original,
                _replacing(original, _rejection()),
                verdict,
                request_id,
            )

        _record_intervention("outbound", reason, safe_price=rounded_price)
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
                # Carried forward, not dropped. These two were left off the
                # hand-built replacement, and a JPY negotiation emitted
                # `action=counter;item=;price=111.12;currency=` — two fields
                # vanishing from the claim that were never in question, so a
                # reader diffing claim against emission saw more changed than
                # did. Dropping them also kept the digests apart by accident on
                # a decision where the substitute happens to equal the
                # proposal; the margin gate now agreeing with psi is what makes
                # the price difference load-bearing instead.
                item_identifier=neg_intent.item_identifier if neg_intent else "",
                item_domain=neg_intent.item_domain if neg_intent else "",
                currency_code=neg_intent.currency_code if neg_intent else "",
                # Deliberately indistinguishable from an ordinary counter. The
                # old text announced "I've reached my final limit", which told
                # the counterparty a guard had fired — and since the substitute
                # is a function of the hidden floor, that is most of the way to
                # inverting it. This reduces distinguishability rather than
                # removing it: a template still reads differently from the
                # model's own prose.
                price=rounded_price,
                message=f"My counter-offer for this item is ${rounded_price:.2f}.",
            ),
        )
        # The substitute price is decidable content, not prose. This write is
        # unconditional and absorbing: whatever a DLP block ahead of it already
        # recorded, the digests now differ, and `override_scope` exists to say
        # exactly that. `gate` is separate and stays with the first gate in this
        # outcome class — see `_Verdict` for why the two accumulate differently.
        verdict.record(_OVERRIDE, reason, "value")
        return await self._finish(
            claim or original, _replacing(original, replacement), verdict, request_id
        )
