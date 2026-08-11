"""
Mints and checks what the Membrane can attest about a decision.

This is not a receipt in the sense VISION means. §5.1.7 holds that a receipt
without a valid verifier signature is not a receipt regardless of any other
field, and neither the signature (§3.7) nor the premise hash (§3.1) is built —
both wait on decisions this code cannot make for itself: who holds the salt, and
what key signs.

So the format calls itself UNSIGNED and `verify` reports what it could not
check. A verifier that answers "valid" while silently skipping the integrity
check is worse than no verifier: it teaches its consumer to rely on a guarantee
nobody made.

See docs/DECISION_RECEIPT.md §3 for the field-by-field design.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

import betterproto
from aura_core_gen.aura.core.v1 import (
    ActionType,
    AssetIntent,
    DecisionDerivation,
    DecisionOutcome,
    DecisionReceipt,
    Intent,
    NegotiationIntent,
    RWAVaultIntent,
    TradeIntent,
)

# The signed format will take its own name rather than flipping a flag on this
# one, so that a consumer written against it cannot be satisfied by a downgrade.
RECEIPT_VERSION = "AURA-RECEIPT-V0-UNSIGNED"

# Width of the human-legible handle, in hex characters. Enough to be distinctive
# in a log line, and not a commitment — nothing is bound until something signs.
_PREFIX_CHARS = 16

# Gates that alter prose and nothing else, so an override under one of them
# leaves claim and emission hashing alike. Naming them is what lets `verify`
# distinguish that legitimate case from a receipt claiming a substitution that
# did not happen.
_PROSE_ONLY_GATES = frozenset({"DLP_BLOCK"})


@dataclass(frozen=True)
class VerificationResult:
    """
    What a reader learned, including what they did not.

    `attested` is deliberately separate from `ok`: everything checkable can pass
    while the receipt remains unattested, and collapsing the two would let
    "nothing was wrong" read as "someone vouched for this".
    """

    ok: bool
    failures: tuple[str, ...] = ()
    unverifiable: tuple[str, ...] = ()
    attested: bool = False


def _action_name(action: Any) -> str:
    """
    `counter`, not `ACTION_TYPE_COUNTER` or `2`.

    The number would be stable too, but the canonical form is meant to be read
    by a human reconciling a receipt against a conversation, and a bare 2 makes
    that a lookup.
    """
    try:
        name = ActionType(int(action)).name or ""
    except (ValueError, TypeError):
        return f"action_{action}"
    return name.removeprefix("ACTION_TYPE_").lower()


def canonical_claim(intent: Intent) -> str:
    """
    The decidable content of a decision, as a stable string.

    Prose is excluded — `reasoning`, `message` and `thought` are the model's free
    text. They are not what the decision decides, and hashing them would make the
    digest irreproducible for anyone who did not receive the byte-exact string.

    The price is rendered to fixed precision because a float is not stable enough
    to hash: 105.0, 105.00 and 105.000000001 must be one claim, and arithmetic
    hands you the last of those.
    """
    params_name, params_value = betterproto.which_one_of(intent, "params")
    action = _action_name(intent.action)

    if params_name == "negotiation" and params_value is not None:
        negotiation: NegotiationIntent = params_value
        return (
            f"action={action};"
            f"item={negotiation.item_identifier};"
            f"price={negotiation.price:.2f}"
        )

    shape = f"action={action};params={params_name or 'none'}"

    # Recording only the shape was the first cut and the wrong half of the job.
    # `action=approve;params=trade` is the same string for every trade there has
    # ever been, so a ten-dollar trade and a nine-million-dollar one produced
    # one digest — a "digest of the decision the Transformer proposed" that does
    # not identify a decision.
    #
    # Harmless while nothing signs a receipt: anyone able to move one onto
    # another Intent can equally mint a fresh one, since `mint` holds no secret.
    # It stops being harmless the moment a signature makes a receipt worth
    # lifting, which is why the collision goes now rather than being inherited
    # by the format that will have something to protect.
    if params_name == "trade" and params_value is not None:
        trade: TradeIntent = params_value
        return (
            f"{shape};"
            f"trade={trade.trade_id};"
            f"asset={trade.asset_identifier};"
            f"price={trade.proposed_price:.2f};"
            f"currency={trade.currency_code}"
        )

    if params_name == "rwa_vault" and params_value is not None:
        vault: RWAVaultIntent = params_value
        # The wallet is part of the claim: same collateral against a different
        # beneficiary is a different decision, not a restatement of one.
        return (
            f"{shape};"
            f"vault={vault.vault_id};"
            f"asset={vault.asset_identifier};"
            f"appraised={vault.appraised_value_usd:.2f};"
            f"ltv={vault.ltv_ratio:.4f};"
            f"wallet={vault.wallet_address}"
        )

    if params_name == "asset" and params_value is not None:
        asset: AssetIntent = params_value
        # The domain is part of the claim: the same identifier in two domains is
        # not the same asset.
        return (
            f"{shape};"
            f"asset={asset.asset_identifier};"
            f"domain={asset.asset_domain};"
            f"asset_action={_action_name(asset.action_type)}"
        )

    # Anything else has no decidable content beyond its shape, and the fallback
    # is a stated boundary rather than an oversight. It covers the bare ERROR
    # Intent the FAILURE_RECOVERY path arrives with, and `audit` / `ui`, which
    # are internal control intents whose content is mostly prose — narratives
    # and rendering instructions. Their receipts identify a shape, not a
    # decision. Any params type that grows outward-facing content needs a branch
    # above, or it inherits the collision this fallback carries.
    return shape


def claim_digest(intent: Intent) -> str:
    """SHA-256 over the canonical claim, lowercase hex."""
    return hashlib.sha256(canonical_claim(intent).encode("utf-8")).hexdigest()


def _content_fields(receipt: DecisionReceipt) -> str:
    """
    The fields the prefix commits to, concatenated in fixed order.

    Order is part of the canonical form: reordering would produce a different
    prefix and fail verification, which is the intended behaviour rather than an
    inconvenience.
    """
    derivation = receipt.derivation or DecisionDerivation()
    return "\n".join(
        [
            receipt.version,
            receipt.claim_hash,
            receipt.ruleset_version,
            derivation.derivation_hash,
            receipt.emission_hash,
            str(int(receipt.outcome)),
            receipt.outcome_gate,
        ]
    )


def _prefix(receipt: DecisionReceipt) -> str:
    digest = hashlib.sha256(_content_fields(receipt).encode("utf-8")).hexdigest()
    return digest[:_PREFIX_CHARS]


def mint(
    claim: Intent,
    emission: Intent,
    outcome: DecisionOutcome,
    outcome_gate: str = "",
    ruleset_version: str = "",
    derivation: DecisionDerivation | None = None,
) -> DecisionReceipt:
    """
    Build the receipt for one decision.

    `claim` is what the Transformer proposed; `emission` is what is actually
    being sent. Passing the same Intent for both is correct when the Membrane
    changed nothing — the two hashes agreeing is then a fact a reader can check,
    not an assumption.
    """
    receipt = DecisionReceipt(
        version=RECEIPT_VERSION,
        claim_hash=claim_digest(claim),
        ruleset_version=ruleset_version,
        emission_hash=claim_digest(emission),
        outcome=outcome,
        outcome_gate=outcome_gate,
    )
    if derivation is not None:
        receipt.derivation = derivation

    receipt.canonical_prefix = _prefix(receipt)
    return receipt


def verify(receipt: DecisionReceipt) -> VerificationResult:
    """
    Re-derive everything checkable without a key, and say what was skipped.

    An unrecognised format version is refused outright rather than checked on a
    best-effort basis. A future signed receipt read by this code would have its
    signature ignored, and answering `ok` on it is exactly the downgrade the
    version string exists to prevent.
    """
    if receipt.version != RECEIPT_VERSION:
        return VerificationResult(
            ok=False,
            failures=(
                f"unknown receipt version {receipt.version!r}; "
                f"this verifier only reads {RECEIPT_VERSION}",
            ),
        )

    failures: list[str] = []

    if receipt.canonical_prefix != _prefix(receipt):
        failures.append("canonical prefix does not match the content fields")

    derivation = receipt.derivation or DecisionDerivation()
    if derivation.gate_sequence or derivation.derivation_hash:
        expected = hashlib.sha256(derivation.gate_sequence.encode("utf-8")).hexdigest()
        if derivation.derivation_hash != expected:
            failures.append("derivation hash does not match the recorded gate sequence")

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNSPECIFIED:
        # Zero is protobuf's default, so an outcome nobody set is
        # indistinguishable from a field never written. A receipt whose central
        # claim is absent must not pass for one that merely had nothing go wrong.
        failures.append("receipt outcome is unspecified")

    changed = receipt.claim_hash != receipt.emission_hash

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE and not changed:
        # A prose-only gate legitimately leaves the two equal, because prose is
        # outside the claim. Any other gate claiming a substitution that left no
        # trace is a receipt describing something that did not happen.
        if receipt.outcome_gate not in _PROSE_ONLY_GATES:
            failures.append(
                "override recorded but claim and emission hash alike, and "
                f"{receipt.outcome_gate!r} is not a prose-only gate"
            )

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT and changed:
        failures.append("emit recorded but the emission does not match the claim")

    return VerificationResult(
        ok=not failures,
        failures=tuple(failures),
        # Named rather than counted, so a caller reads what is missing instead
        # of a number they have to look up.
        unverifiable=("signature", "premises", "policy"),
        attested=False,
    )
