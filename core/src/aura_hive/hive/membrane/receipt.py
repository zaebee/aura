"""
Mints and checks what the Membrane can attest about a decision.

Two formats, and the difference is the point. `AURA-RECEIPT-V2` carries an
EIP-712 signature over its content fields and can be attributed to the agent
that produced it. `AURA-RECEIPT-V2-UNSIGNED` carries everything else and says in
its own name that it carries no attestation, which is what a deployment with no
key configured honestly produces.

The number is the format generation; the suffix is attestation. V0 and V1 read
as though they were successive formats, but they were one format signed and
unsigned — the generation never actually changed between them. V2 is the first
real generation bump: `issued_at`, `decision_id` and `request_id` enter the
signed content, binding a receipt to the one decision it describes instead of
to an equivalence class of decisions that happen to share a claim and an
emission. V0 and V1 are deleted rather than deprecated — no persisted receipt
exists anywhere to read back in the old shape.

They are separate names rather than one name and a flag, so a consumer written
against the signed format cannot be satisfied by a downgrade, and `verify`
refuses a version it does not recognise instead of best-effort checking one.

`verify` also reports what it could not check. The premise hash (§3.1) is still
unbuilt — and on our premises it can only ever be a commitment opened to a
trusted party, never a counterparty-verifiable field, because they are
low-entropy enough that anyone holding the salt can recover them. A verifier
answering "valid" while silently skipping a check teaches its consumer to rely
on a guarantee nobody made.

See docs/DECISION_RECEIPT.md §3 for the field-by-field design.
"""

import hashlib
from dataclasses import dataclass, replace
from typing import Any

import betterproto
from aura_core import decision_outcome_name
from aura_core_gen.aura.core.v1 import (
    ActionType,
    AssetIntent,
    DecisionDerivation,
    DecisionOutcome,
    DecisionReceipt,
    Intent,
    NegotiationIntent,
    ReceiptSignature,
    RWAVaultIntent,
    TradeIntent,
)
from eth_account import Account
from eth_account.messages import encode_typed_data

# The signed format takes its own name rather than flipping a flag on the
# unsigned one, so a consumer written against it cannot be satisfied by a
# downgrade. A deployment with no key configured produces the unsigned format
# and says so — that is the honest report, not an error.
RECEIPT_VERSION = "AURA-RECEIPT-V2-UNSIGNED"
SIGNED_VERSION = "AURA-RECEIPT-V2"

# Kept DISTINCT from the domain TradeIntent signs under (`HackathonRiskRouter`).
#
# This is the whole reason reusing the agent's spending key is acceptable: with
# separate domain separators a receipt signature is not a valid trade
# authorisation and a trade authorisation is not a valid receipt. `signing_payload`
# also omits `verifyingContract` — a receipt has no contract — which makes the
# domain structurally different rather than merely differently named.
RECEIPT_EIP712_DOMAIN = "AuraDecisionReceipt"
RECEIPT_EIP712_VERSION = "1"
_SIGNATURE_SCHEME = "eip712"

# Width of the human-legible handle, in hex characters. Enough to be distinctive
# in a log line, and not a commitment — nothing is bound until something signs.
_PREFIX_CHARS = 16


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
    The fields the prefix and the signature commit to, in fixed order.

    Order is part of the canonical form: reordering produces a different prefix
    and fails verification, which is intended rather than inconvenient.

    `issued_at`, `decision_id` and `request_id` are here rather than alongside
    because binding that is not signed is decorative — anyone can rewrite it.
    """
    derivation = receipt.derivation or DecisionDerivation()
    return "\n".join(
        [
            receipt.version,
            receipt.issued_at,
            receipt.decision_id,
            receipt.request_id,
            receipt.claim_hash,
            receipt.ruleset_version,
            derivation.derivation_hash,
            receipt.emission_hash,
            decision_outcome_name(receipt.outcome),
            receipt.outcome_gate,
            receipt.override_scope,
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
    issued_at: str = "",
    decision_id: str = "",
    request_id: str = "",
    override_scope: str = "",
) -> DecisionReceipt:
    """
    Build the receipt for one decision.

    `claim` is what the Transformer proposed; `emission` is what is being sent.
    Passing the same Intent for both is correct when the Membrane changed
    nothing — the two hashes agreeing is then a fact a reader can check.
    """
    receipt = DecisionReceipt(
        version=RECEIPT_VERSION,
        claim_hash=claim_digest(claim),
        ruleset_version=ruleset_version,
        emission_hash=claim_digest(emission),
        outcome=outcome,
        outcome_gate=outcome_gate,
        issued_at=issued_at,
        decision_id=decision_id,
        request_id=request_id,
        override_scope=override_scope,
    )
    if derivation is not None:
        receipt.derivation = derivation

    receipt.canonical_prefix = _prefix(receipt)
    return receipt


def signing_payload(receipt: DecisionReceipt, chain_id: int) -> dict[str, Any]:
    """
    EIP-712 structured data for a receipt, as it will read once signed.

    Computed against the signed form's content fields — `version` is one of
    them, so signing the unsigned form would produce an attestation over a
    document that no longer exists the moment the version is bumped.
    """
    probe = replace(receipt, version=SIGNED_VERSION)
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "DecisionReceipt": [{"name": "content", "type": "string"}],
        },
        "domain": {
            "name": RECEIPT_EIP712_DOMAIN,
            "version": RECEIPT_EIP712_VERSION,
            "chainId": chain_id,
        },
        "primaryType": "DecisionReceipt",
        "message": {"content": _content_fields(probe)},
    }


def signed(
    receipt: DecisionReceipt, signer: str, signature: str, chain_id: int
) -> DecisionReceipt:
    """
    A copy of the receipt bearing the attestation, at the signed version.

    Returns a new receipt rather than mutating: the version and the prefix both
    change, and a half-updated receipt in a caller's hand is a document that
    verifies as neither format.
    """
    attested = replace(
        receipt,
        version=SIGNED_VERSION,
        signature=ReceiptSignature(
            scheme=_SIGNATURE_SCHEME,
            domain=RECEIPT_EIP712_DOMAIN,
            domain_version=RECEIPT_EIP712_VERSION,
            chain_id=chain_id,
            signer=signer,
            signature=signature if signature.startswith("0x") else f"0x{signature}",
        ),
    )
    attested.canonical_prefix = _prefix(attested)
    return attested


def _check_signature(receipt: DecisionReceipt) -> list[str]:
    """
    Recover the signer from the attestation and confirm it is who is claimed.

    Needs no key material — verification is public by construction, which is
    why it lives here rather than behind the protein that holds the private
    key. The domain is rebuilt from the receipt's own fields, so a reader needs
    no out-of-band configuration.
    """
    signature = receipt.signature
    if signature is None or not signature.signature:
        return ["receipt claims the signed format but carries no signature"]

    payload = signing_payload(receipt, chain_id=signature.chain_id)
    try:
        recovered = Account.recover_message(
            encode_typed_data(full_message=payload), signature=signature.signature
        )
    except Exception as exc:
        return [f"signature could not be recovered: {exc}"]

    if recovered.lower() != signature.signer.lower():
        return [
            f"signature recovers to {recovered}, not the signer "
            f"{signature.signer} the receipt claims"
        ]

    return []


def verify(receipt: DecisionReceipt) -> VerificationResult:
    """
    Re-derive everything checkable without a key, and say what was skipped.

    An unrecognised format version is refused outright rather than checked on a
    best-effort basis. A future signed receipt read by this code would have its
    signature ignored, and answering `ok` on it is exactly the downgrade the
    version string exists to prevent.
    """
    if receipt.version not in (RECEIPT_VERSION, SIGNED_VERSION):
        return VerificationResult(
            ok=False,
            failures=(
                f"unknown receipt version {receipt.version!r}; "
                f"this verifier reads {RECEIPT_VERSION} and {SIGNED_VERSION}",
            ),
        )

    attested = receipt.version == SIGNED_VERSION
    failures: list[str] = _check_signature(receipt) if attested else []

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

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE:
        # Checked in both directions. A value-scoped override that left the
        # digests alike describes a substitution that did not happen; a
        # prose-scoped one whose digests differ describes prose reaching the
        # decidable content, which prose is defined not to do.
        if receipt.override_scope == "prose" and changed:
            failures.append(
                "override scoped to prose but the claim and emission digests differ"
            )
        elif receipt.override_scope != "prose" and not changed:
            failures.append(
                "override recorded but claim and emission hash alike, and the "
                f"scope is {receipt.override_scope or 'unset'!r} rather than 'prose'"
            )

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT and changed:
        failures.append("emit recorded but the emission does not match the claim")

    # A rule set judged this decision, so it must say how. The witness used to
    # be optional: a receipt could name the rules and record nothing about their
    # application, and verify would pass it.
    derivation_missing = not (derivation.gate_sequence or derivation.derivation_hash)
    judged = receipt.outcome in (
        DecisionOutcome.DECISION_OUTCOME_EMIT,
        DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
    )
    if judged and receipt.ruleset_version and derivation_missing:
        failures.append(
            f"receipt cites rule set {receipt.ruleset_version!r} but carries no derivation"
        )

    # Computed, not a constant. A caller reads what this verifier could not
    # establish about THIS receipt, so the list stays true as fields land.
    unverifiable: list[str] = []
    if not attested:
        unverifiable.append("signature")
    # Always. verify() is handed the receipt and never the Intent, so it cannot
    # establish that claim_hash digests the decision the model actually made.
    # Naming it is the difference between a verifier and a rubber stamp.
    unverifiable.append("emission_content")
    if not receipt.issued_at:
        unverifiable.append("freshness")
    # Still unbuilt; see DECISION_RECEIPT.md §3.1 and §3.5.
    unverifiable.extend(["premises", "policy"])

    return VerificationResult(
        ok=not failures,
        failures=tuple(failures),
        unverifiable=tuple(unverifiable),
        # Only when a signature was present AND recovered to the claimed signer.
        # A failed check leaves this False rather than True-with-failures, so a
        # caller reading one field cannot get the wrong answer.
        attested=attested and not failures,
    )
