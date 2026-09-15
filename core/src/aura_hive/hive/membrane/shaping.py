from datetime import UTC, datetime
from typing import Any, cast

import structlog
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import ActionType, DecisionReceipt, Intent

from .receipt import mint
from .verdict import _Verdict

logger = structlog.get_logger(__name__)


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


def _rejection(reasoning: str = "Membrane: post-condition not established") -> Intent:
    """
    What leaves when the Membrane cannot stand behind a decision.

    Deliberately carries no price and no reason the counterparty can read: the
    decision was stopped because we could not establish our own guarantee, and
    saying which clause failed would describe the policy boundary to the party
    the policy exists to hold at arm's length.

    The default names the ψ failure, which is the common case. G3 passes its
    own: refusing because the rule set cannot be evaluated is a different fact
    from refusing because it was evaluated and failed, and the internal
    `reasoning` is where an operator reads which one happened.
    """
    return Intent(
        action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
        reasoning=reasoning,
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


def _quoted_price(price: float, currency_code: str) -> str:
    """
    A price in the denomination it is actually in.

    Both messages the Membrane writes used to hardcode `$`, so a JPY
    negotiation was told `$111.12` — the structured `currency_code` saying one
    thing and the prose beside it another, on the one path where the Membrane
    rather than the model is choosing the words.

    No symbol table: mapping codes to glyphs is a localisation problem this
    module has no business holding an opinion about, and getting it wrong is
    the failure being fixed. The code itself is unambiguous in every currency.
    An unstated denomination renders as a bare number — two call sites
    legitimately have no source for one (§3.2) and the naive f-string would
    leave a space before the full stop.
    """
    return f"{price:.2f} {currency_code}".rstrip()


def _neutral_price_message(action: Any, price: float, currency_code: str) -> str:
    """
    State the price without stating that a guard produced it.

    Phrased from the action rather than fixed, because the DLP block keeps the
    model's action: sanitising an ACCEPT used to emit "My counter-offer for this
    item is $X", which contradicts the `accepted` result the counterparty
    receives alongside it. A message that disagrees with the decision beside it
    is its own tell.
    """
    quoted = _quoted_price(price, currency_code)
    if action == ActionType.ACTION_TYPE_ACCEPT:
        return f"I accept your offer at {quoted}."
    return f"My counter-offer for this item is {quoted}."


def _action_label(action: Any) -> str:
    """Safely convert ActionType or raw int to a lowercase name string."""
    try:
        name = ActionType(int(action)).name
        return name.lower() if name else f"action_{int(action)}"
    except (ValueError, TypeError, AttributeError):
        return f"action_{action}"
