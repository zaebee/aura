"""
The shape a machine consumer actually receives.

The receipt exists to be checked by someone outside this process, so the JSON
has to carry enough for them to recover the signer themselves rather than
calling our code. Two properties do most of that work: the signature block is
self-describing, and the fields that make up the signed content appear exactly
as they were signed.
"""

from api_gateway.main import receipt_to_json
from aura_core_gen.aura.core.v1 import (
    DecisionDerivation,
    DecisionOutcome,
    DecisionReceipt,
    ReceiptSignature,
)

SIGNED = DecisionReceipt(
    version="AURA-RECEIPT-V1",
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


class TestTheOutcomeIsNamed:
    def test_it_travels_as_the_string_that_was_signed(self) -> None:
        """
        Not the protobuf integer. The signature covers this name, so publishing
        the number would leave a consumer to map it back — and a mapping step
        inside a signature reconstruction is where they get it wrong.
        """
        assert receipt_to_json(SIGNED)["outcome"] == "override"


class TestTheSignatureIsSelfDescribing:
    def test_the_domain_travels_with_the_signature(self) -> None:
        """
        A consumer rebuilds the EIP-712 domain from these fields alone. Without
        them they would need to know how we are configured, and a receipt only
        checkable by someone who already knows that is not much of a receipt.
        """
        signature = receipt_to_json(SIGNED)["signature"]

        assert signature["domain"] == "AuraDecisionReceipt"
        assert signature["domain_version"] == "1"
        assert signature["chain_id"] == 84532
        assert signature["scheme"] == "eip712"
        assert signature["signer"] == "0xabc"


class TestAnUnsignedReceiptCannotPassForASignedOne:
    def test_the_version_says_so(self) -> None:
        unsigned = DecisionReceipt(
            version="AURA-RECEIPT-V0-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            canonical_prefix="0123456789abcdef",
        )

        assert receipt_to_json(unsigned)["version"] == "AURA-RECEIPT-V0-UNSIGNED"

    def test_the_signature_is_null_rather_than_an_empty_shape(self) -> None:
        """
        An empty signature object invites a consumer to check its fields and
        find blanks. `null` cannot be misread as an attestation that happened to
        have no content.
        """
        unsigned = DecisionReceipt(
            version="AURA-RECEIPT-V0-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
        )

        assert receipt_to_json(unsigned)["signature"] is None


class TestTheReceiptIsNested:
    def test_it_is_one_object_rather_than_spread_across_keys(self) -> None:
        """
        Deferred step 4 adds a premise hash and a policy stamp to this same
        message. Nesting keeps that open; flattening would make each new field a
        separate decision about the endpoint's top-level shape.
        """
        rendered = receipt_to_json(SIGNED)

        assert set(rendered) == {
            "version",
            "canonical_prefix",
            "outcome",
            "outcome_gate",
            "claim_hash",
            "emission_hash",
            "ruleset_version",
            "derivation",
            "signature",
        }
        assert rendered["derivation"]["gate_sequence"].startswith("G1_")


class TestNothingHiddenNothingInvented:
    def test_a_receipt_with_no_derivation_reports_none(self) -> None:
        """
        Membrane-level refusals consult no rule set, so they have no derivation.
        An empty object would assert one that never ran.
        """
        bare = DecisionReceipt(
            version="AURA-RECEIPT-V0-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_REFUSE,
            outcome_gate="KYC_FAILURE",
        )

        assert receipt_to_json(bare)["derivation"] is None

    def test_an_explicit_none_renders_as_nothing(self) -> None:
        """
        The defensive case, not the real one. betterproto never hands back None
        for a message field — see TestAnUnsetReceiptIsAbsence for the shape an
        actual receipt-less response has, which is what this test originally
        claimed to cover and did not.
        """
        assert receipt_to_json(None) is None


class TestAnUnsetReceiptIsAbsence:
    """
    betterproto default-constructs a message field on access rather than
    returning None, so `response.receipt` is a DecisionReceipt of blanks when
    the core never set one — never `None`.

    The first cut checked `receipt is None`, which therefore never fired, and
    the test that covered it passed `None` explicitly: it verified a case the
    real path does not produce and missed the one it does. Emptiness here is a
    property of the value, not of the reference.
    """

    def test_a_default_constructed_receipt_renders_as_nothing(self) -> None:
        assert receipt_to_json(DecisionReceipt()) is None

    def test_the_response_of_a_deployment_that_minted_nothing_carries_no_receipt(
        self,
    ) -> None:
        """The shape a client sees, taken off an actual response object."""
        from aura_core_gen.aura.negotiation.v1 import NegotiateResponse

        assert receipt_to_json(NegotiateResponse().receipt) is None

    def test_a_receipt_with_a_version_is_still_rendered(self) -> None:
        """The check must not swallow a real receipt that happens to be sparse."""
        sparse = DecisionReceipt(
            version="AURA-RECEIPT-V0-UNSIGNED",
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
        )

        rendered = receipt_to_json(sparse)

        assert rendered is not None
        assert rendered["version"] == "AURA-RECEIPT-V0-UNSIGNED"
