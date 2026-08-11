"""
The two audiences a decision receipt has, and what each sees.

`receipt_to_json` is what the HTTP response gives a negotiating counterparty:
a handle they can cite in a dispute, and nothing that lets them reconstruct
the hidden floor price. `outcome_gate` names the rule that fired, the rule set
maps that gate to a substitute-price strategy, and the price is already in the
response — together that recovers the floor, so none of it, nor the binding
fields (`issued_at`, `decision_id`, `request_id`, `override_scope`), reach the
counterparty.

`receipt_to_json_full` is for the auditor the receipt is actually addressed
to. It carries everything, and the reasons for its shape are the same as
before the split: the signature block is self-describing, so a consumer
rebuilds the EIP-712 domain and calls `ecrecover` without knowing how we are
configured, and `outcome` travels as the name that was signed rather than its
protobuf integer.
"""

from api_gateway.main import receipt_to_json, receipt_to_json_full
from aura_core_gen.aura.core.v1 import (
    DecisionDerivation,
    DecisionOutcome,
    DecisionReceipt,
    ReceiptSignature,
)

SIGNED = DecisionReceipt(
    version="AURA-RECEIPT-V2",
    claim_hash="a" * 64,
    ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
    derivation=DecisionDerivation(
        gate_sequence="G1_PRICE_POSITIVE:pass:price", derivation_hash="b" * 64
    ),
    emission_hash="c" * 64,
    outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
    outcome_gate="FLOOR_PRICE_VIOLATION",
    canonical_prefix="c0ffee1234abcd56",
    signature=ReceiptSignature(
        scheme="eip712",
        domain="AuraDecisionReceipt",
        domain_version="1",
        chain_id=84532,
        signer="0xabc",
        signature="0xdef",
    ),
)


def a_signed_override_receipt() -> DecisionReceipt:
    """
    A fully populated receipt, so a field surviving the trim is visible as a
    key that should not be there rather than as an empty string nobody notices.
    """
    return DecisionReceipt(
        version="AURA-RECEIPT-V2",
        canonical_prefix="c0ffee1234abcd56",
        claim_hash="a" * 64,
        emission_hash="b" * 64,
        ruleset_version="guard/negotiation@2.0.0+46cc0e38ca4f895c",
        outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
        outcome_gate="FLOOR_PRICE_VIOLATION",
        override_scope="value",
        issued_at="2026-08-11T10:00:00Z",
        decision_id="d-1",
        request_id="r-1",
    )


class TestTheClientSeesAHandleAndNothingElse:
    """What `receipt_to_json` gives the counterparty over HTTP."""

    def test_only_the_version_and_the_prefix_are_rendered(self) -> None:
        """
        The receipt is addressed to an auditor. Nothing in it means anything to
        the counterparty, and `outcome_gate` plus the price they received is
        most of the way to inverting the floor.
        """
        rendered = receipt_to_json(a_signed_override_receipt())
        assert set(rendered) == {"version", "canonical_prefix"}

    def test_the_hashes_and_the_gate_are_absent(self) -> None:
        rendered = receipt_to_json(a_signed_override_receipt())
        for gone in (
            "outcome",
            "outcome_gate",
            "claim_hash",
            "emission_hash",
            "ruleset_version",
            "derivation",
            "signature",
        ):
            assert gone not in rendered

    def test_the_binding_fields_are_absent(self) -> None:
        """
        `override_scope` in particular tells a counterparty whether the
        substitution touched the price or only the wording — exactly the kind
        of inference the trim exists to stop.
        """
        rendered = receipt_to_json(a_signed_override_receipt())
        for gone in ("issued_at", "decision_id", "request_id", "override_scope"):
            assert gone not in rendered

    def test_a_receiptless_response_renders_null(self) -> None:
        """
        betterproto default-constructs a message field on access, so
        `receipt is None` is dead code — the check is by value.
        """
        assert receipt_to_json(DecisionReceipt()) is None

    def test_an_explicit_none_renders_as_nothing(self) -> None:
        """
        The defensive case, not the real one. betterproto never hands back None
        for a message field — see test_a_receiptless_response_renders_null for
        the shape an actual receipt-less response has.
        """
        assert receipt_to_json(None) is None

    def test_the_response_of_a_deployment_that_minted_nothing_carries_no_receipt(
        self,
    ) -> None:
        """The shape a client sees, taken off an actual response object."""
        from aura_core_gen.aura.negotiation.v1 import NegotiateResponse

        assert receipt_to_json(NegotiateResponse().receipt) is None

    def test_a_receipt_with_a_version_is_still_rendered(self) -> None:
        """The check must not swallow a real receipt that happens to be sparse."""
        sparse = DecisionReceipt(
            version="AURA-RECEIPT-V2-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
        )

        rendered = receipt_to_json(sparse)

        assert rendered is not None
        assert rendered["version"] == "AURA-RECEIPT-V2-UNSIGNED"


class TestTheFullRendererKeepsEverything:
    """
    What `receipt_to_json_full` renders — for the log line an auditor's
    tooling reads, never for the HTTP response.
    """

    def test_it_carries_the_binding_fields(self) -> None:
        rendered = receipt_to_json_full(a_signed_override_receipt())
        for field in (
            "issued_at",
            "decision_id",
            "request_id",
            "override_scope",
            "outcome_gate",
            "claim_hash",
            "emission_hash",
        ):
            assert field in rendered

    def test_it_is_one_nested_object_with_the_full_shape(self) -> None:
        """
        Deferred step 4 [core] adds a premise hash and a policy stamp to this
        same message. Nesting keeps that open; flattening would make each new
        field a separate decision about the shape of whatever renders this.
        """
        rendered = receipt_to_json_full(SIGNED)

        assert set(rendered) == {
            "version",
            "canonical_prefix",
            "issued_at",
            "decision_id",
            "request_id",
            "override_scope",
            "outcome",
            "outcome_gate",
            "claim_hash",
            "emission_hash",
            "ruleset_version",
            "derivation",
            "signature",
        }
        assert rendered["derivation"]["gate_sequence"].startswith("G1_")

    def test_the_outcome_travels_as_the_string_that_was_signed(self) -> None:
        """
        Not the protobuf integer. The signature covers this name, so publishing
        the number would leave a consumer to map it back — and a mapping step
        inside a signature reconstruction is where they get it wrong.
        """
        assert receipt_to_json_full(SIGNED)["outcome"] == "override"

    def test_the_signature_is_self_describing(self) -> None:
        """
        A consumer rebuilds the EIP-712 domain from these fields alone. Without
        them they would need to know how we are configured, and a receipt only
        checkable by someone who already knows that is not much of a receipt.
        """
        signature = receipt_to_json_full(SIGNED)["signature"]

        assert signature["domain"] == "AuraDecisionReceipt"
        assert signature["domain_version"] == "1"
        assert signature["chain_id"] == 84532
        assert signature["scheme"] == "eip712"
        assert signature["signer"] == "0xabc"

    def test_the_signature_is_null_rather_than_an_empty_shape_when_unsigned(
        self,
    ) -> None:
        """
        An empty signature object invites a consumer to check its fields and
        find blanks. `null` cannot be misread as an attestation that happened to
        have no content.
        """
        unsigned = DecisionReceipt(
            version="AURA-RECEIPT-V2-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
        )

        assert receipt_to_json_full(unsigned)["signature"] is None

    def test_a_receipt_with_no_derivation_reports_none(self) -> None:
        """
        Membrane-level refusals consult no rule set, so they have no derivation.
        An empty object would assert one that never ran.
        """
        bare = DecisionReceipt(
            version="AURA-RECEIPT-V2-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_REFUSE,
            outcome_gate="KYC_FAILURE",
        )

        assert receipt_to_json_full(bare)["derivation"] is None

    def test_a_default_constructed_receipt_renders_as_nothing(self) -> None:
        """
        Same guard, same reasoning as the public renderer: betterproto
        default-constructs a message field on access rather than returning
        None, so the check is by value (`version`) and not by identity.
        """
        assert receipt_to_json_full(DecisionReceipt()) is None

    def test_an_explicit_none_renders_as_nothing(self) -> None:
        assert receipt_to_json_full(None) is None
