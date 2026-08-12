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

    First gate wins. A decision that trips DLP and then the floor check records
    DLP_BLOCK, the earlier one: reporting every gate that fired would hand an
    adversary an oracle over the policy configuration — probe with crafted
    offers, read back which invariants answered, and the shape of the hidden
    floor falls out. This constrains only what is recorded; every gate still
    executes.

    `override_scope` rides the same first-wins call as `gate` rather than
    being a field a call site sets on its own. Two bugs followed from letting
    it be independent: a later, unrelated `record()` call (e.g. the
    post-condition failing after DLP already fired) left a stale scope
    describing a gate that no longer explains the final outcome, and a second
    OVERRIDE-outcome call downstream of the first could overwrite the scope
    for a gate it did not win against — `gate` staying DLP_BLOCK while
    `override_scope` said "value" because the *safe-offer* site, not the DLP
    site, wrote last. Pairing the write with the same guard that already
    decides which gate is reported closes both: whatever `_gate_scope` holds
    was written in the same call that produced `gate`, so it can never
    describe a different intervention. `override_scope` is exposed as a
    property recomputed from `self.outcome` on every read rather than a
    cached value some call site is trusted to clear, so a decision that moves
    past OVERRIDE (the post-condition rejecting the DLP-sanitised offer, for
    instance) can never leave the property non-empty — there is no field left
    to forget to reset.
    """

    outcome: DecisionOutcome = _EMIT
    gate: str = ""
    ruleset_version: str = ""
    derivation: DecisionDerivation | None = None
    _gate_scope: str = field(default="", repr=False)

    def record(self, outcome: DecisionOutcome, gate: str, scope: str = "") -> None:
        self.outcome = outcome
        if not self.gate:
            self.gate = gate
            self._gate_scope = scope
            if outcome == _OVERRIDE and not scope:
                # A call site that reports OVERRIDE must say whether the
                # substitution touched prose or value — `override_scope`
                # trusts this rather than re-deriving it, and a call site that
                # forgets should fail loudly in its own tests rather than
                # ship a receipt that claims OVERRIDE with nothing to say
                # about it.
                raise ValueError(
                    f"gate {gate!r} recorded outcome OVERRIDE with no scope; "
                    "every OVERRIDE call site must pass 'prose' or 'value'"
                )

    @property
    def override_scope(self) -> str:
        """
        The scope of the intervention `gate` names, or "" when the final
        outcome is not OVERRIDE.

        Derived from `self.outcome` on every read instead of stored plainly,
        so it cannot outlive the OVERRIDE outcome that justified it — see the
        class docstring for the failure this closes.
        """
        return self._gate_scope if self.outcome == _OVERRIDE else ""

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


def _is_signed(receipt: DecisionReceipt) -> bool:
    """
    Whether an attestation is attached — not whether it is valid.

    Checked by value rather than by object. betterproto messages define their
    own falsiness, so `bool(receipt.signature)` does discriminate a signed
    receipt from an unsigned one; but a signature block carrying a scheme and no
    signature would still read as truthy, and the log's notion of signed should
    not be weaker than `verify`'s, which already reads the value.

    Deliberately NOT called `attested`. That word belongs to `verify` and means
    the signature recovered to the signer the receipt claims. This function
    recovers nothing, and a log claiming attestation nobody performed is the
    same overstatement `VerificationResult` separates `ok` from `attested` to
    avoid — in a cheaper place.
    """
    signature = receipt.signature
    return signature is not None and bool(signature.signature)


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

        **The Intent passed in is never modified.** Every path that changes
        anything — the two refusals, the safe-offer override, the DLP
        sanitisation — builds a replacement and leaves the caller's object
        alone.

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
                        "context": {"floor_price": floor_price},
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
                        message=f"My counter-offer for this item is ${neg_intent.price:.2f}.",
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

        # 3. Call Guard Protein for validation
        if not self.registry:
            return await self._finish(claim, decision, verdict, request_id)

        internal_cost = _context_number(ctx_meta, "internal_cost", floor_price)
        guard_context = {
            "floor_price": floor_price,
            "internal_cost": internal_cost,
            "request_id": request_id,
        }

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
                decision, safe_price, reason, verdict, guard_context, request_id, claim
            )

        if not await self._postcondition_holds(price, guard_context, verdict):
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
        _record_intervention("outbound", reason, safe_price=round(safe_price, 2))
        rounded_price = round(safe_price, 2)

        if not await self._postcondition_holds(rounded_price, guard_context, verdict):
            return await self._finish(
                claim or original,
                _replacing(original, _rejection()),
                verdict,
                request_id,
            )
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
        # The substitute price is decidable content, not prose: claim and
        # emission differ here, but the scope is set uniformly with the DLP
        # site rather than left to be inferred from "the hashes happened to
        # differ" — a verifier checking the pairing reads this instead of a
        # hardcoded list of which gates are prose-only. First-gate-wins still
        # applies: this write only sticks when nothing recorded a gate
        # earlier in the same decision (e.g. a DLP block ahead of this one),
        # in which case `gate` and `override_scope` both stay the earlier
        # call's.
        verdict.record(_OVERRIDE, reason, "value")
        return await self._finish(
            original, _replacing(original, replacement), verdict, request_id
        )
