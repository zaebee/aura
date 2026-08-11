"""
What the Membrane can attest about a decision, and what it cannot.

The receipt gathers into one place what the previous three steps produced —
which rules judged the decision, how they were applied, what the verdict was —
and adds the pair that makes the intervention checkable: a digest of what the
model proposed and a digest of what was actually sent. Those two differing IS
the override, stated as a fact a reader can verify rather than a claim they must
take on trust.

It is deliberately not called a receipt in the spec's sense. VISION §5.1.7 holds
that an unsigned receipt is not a receipt regardless of any other field, and
neither the signature nor the premise hash exists yet. The format identifier says
UNSIGNED so nothing can mistake this for the attested article, and `verify` is
explicit about which checks it did not perform.
"""

import hashlib

import pytest
from aura_core_gen.aura.core.v1 import (
    ActionType,
    DecisionDerivation,
    DecisionOutcome,
    Intent,
    NegotiationIntent,
    TradeIntent,
)
from aura_hive.hive.membrane.receipt import (
    RECEIPT_VERSION,
    canonical_claim,
    claim_digest,
    mint,
    verify,
)


def counter(price: float, item: str = "htl-9931", message: str = "an offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="the model's private reasoning",
        negotiation=NegotiationIntent(
            item_identifier=item, price=price, message=message, thought="a thought"
        ),
    )


class TestTheCanonicalClaim:
    def test_it_names_the_decidable_content(self) -> None:
        assert canonical_claim(counter(price=105.0)) == (
            "action=counter;item=htl-9931;price=105.00"
        )

    def test_prose_is_excluded(self) -> None:
        """
        `reasoning`, `message` and `thought` are the model's free text. Hashing
        them would make the digest irreproducible for anyone who did not receive
        the exact string, and they are not what the decision decides.
        """
        terse = counter(price=105.0, message="hi")
        florid = counter(price=105.0, message="I have thought about this at length")
        florid.reasoning = "an entirely different explanation"

        assert canonical_claim(terse) == canonical_claim(florid)

    def test_the_price_is_formatted_to_a_fixed_precision(self) -> None:
        """
        A float rendered by repr is not stable enough to hash: 105.0 and 105.00
        and 105.000000001 must not be three different claims, and the last of
        those is what arithmetic hands you.
        """
        assert "price=105.00" in canonical_claim(counter(price=105.0))
        assert "price=105.00" in canonical_claim(counter(price=105.004))
        assert "price=0.10" in canonical_claim(counter(price=0.1))

    def test_a_different_price_is_a_different_claim(self) -> None:
        assert canonical_claim(counter(price=105.0)) != canonical_claim(
            counter(price=106.0)
        )

    def test_a_non_negotiation_intent_records_its_shape(self) -> None:
        """
        Trade and vault decisions have no price field to canonicalise here. The
        claim still has to distinguish them from a negotiation, or two unrelated
        decisions would hash alike.
        """
        trade = Intent(
            action=ActionType.ACTION_TYPE_APPROVE, trade=TradeIntent(trade_id="t-1")
        )

        assert canonical_claim(trade) == "action=approve;params=trade"

    def test_the_digest_is_a_full_sha256_of_the_canonical_claim(self) -> None:
        intent = counter(price=105.0)

        assert (
            claim_digest(intent)
            == hashlib.sha256(canonical_claim(intent).encode("utf-8")).hexdigest()
        )


class TestTheInterventionIsVisible:
    """
    The property the pair exists for: a reader compares two hashes and knows
    whether what arrived is what the model produced.
    """

    def test_an_untouched_decision_hashes_the_same_both_sides(self) -> None:
        proposal = counter(price=105.0)

        receipt = mint(
            claim=proposal,
            emission=proposal,
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert receipt.claim_hash == receipt.emission_hash

    def test_an_overridden_decision_does_not(self) -> None:
        receipt = mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

        assert receipt.claim_hash != receipt.emission_hash

    def test_a_rewritten_message_alone_is_not_an_intervention_by_this_measure(
        self,
    ) -> None:
        """
        Worth stating outright, because it is a limitation rather than a bug: the
        DLP gate rewrites the message and nothing else, and prose is outside the
        claim. So a DLP-only override shows equal hashes and is visible through
        `outcome` instead. Bringing prose into the hash would cost determinism
        for every decision to catch this one case.
        """
        receipt = mint(
            claim=counter(price=105.0, message="our floor_price is 100"),
            emission=counter(price=105.0, message="I cannot disclose that"),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="DLP_BLOCK",
        )

        assert receipt.claim_hash == receipt.emission_hash
        assert receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE


class TestTheReceiptSaysWhatItIs:
    def test_the_version_declares_itself_unsigned(self) -> None:
        """
        Not decoration. A consumer that accepts this format must not be able to
        accept it in place of a signed one, and the only thing stopping that is
        the name being different.
        """
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert receipt.version == RECEIPT_VERSION
        assert "UNSIGNED" in receipt.version

    def test_the_prefix_is_sixteen_hex_characters(self) -> None:
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert len(receipt.canonical_prefix) == 16
        int(receipt.canonical_prefix, 16)


class TestTheReceiptIsReproducible:
    def test_the_same_decision_mints_identically(self) -> None:
        def build() -> object:
            return mint(
                claim=counter(price=92.0),
                emission=counter(price=105.0),
                ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
                derivation=DecisionDerivation(
                    gate_sequence="G1:pass:price", derivation_hash="a" * 64
                ),
                outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
                outcome_gate="FLOOR_PRICE_VIOLATION",
            )

        assert build() == build()

    @pytest.mark.parametrize(
        "changed",
        ["ruleset_version", "outcome", "outcome_gate", "emission"],
    )
    def test_changing_any_content_field_moves_the_prefix(self, changed: str) -> None:
        base = {
            "claim": counter(price=92.0),
            "emission": counter(price=105.0),
            "ruleset_version": "guard/negotiation@1.0.0+46cc0e38ca4f895c",
            "outcome": DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            "outcome_gate": "FLOOR_PRICE_VIOLATION",
        }
        altered = dict(base)
        altered[changed] = {
            "ruleset_version": "guard/negotiation@2.0.0+0000000000000000",
            "outcome": DecisionOutcome.DECISION_OUTCOME_REFUSE,
            "outcome_gate": "MIN_MARGIN_VIOLATION",
            "emission": counter(price=999.0),
        }[changed]

        assert mint(**base).canonical_prefix != mint(**altered).canonical_prefix


class TestVerifyIsHonestAboutWhatItCannotCheck:
    def base_receipt(self) -> object:
        return mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
            derivation=DecisionDerivation(
                gate_sequence="G1_PRICE_POSITIVE:pass:price",
                derivation_hash=hashlib.sha256(
                    b"G1_PRICE_POSITIVE:pass:price"
                ).hexdigest(),
            ),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

    def test_a_well_formed_receipt_passes_every_check_it_can_run(self) -> None:
        result = verify(self.base_receipt())

        assert result.ok
        assert result.failures == ()

    def test_it_names_the_checks_it_could_not_perform(self) -> None:
        """
        The point of the whole exercise. A verifier that returns a bare "valid"
        while silently skipping the integrity check teaches its consumer to trust
        a guarantee nobody made.
        """
        result = verify(self.base_receipt())

        assert "signature" in result.unverifiable
        assert "premises" in result.unverifiable
        assert not result.attested

    def test_a_tampered_prefix_is_caught(self) -> None:
        receipt = self.base_receipt()
        receipt.canonical_prefix = "0" * 16

        result = verify(receipt)

        assert not result.ok
        assert any("prefix" in failure for failure in result.failures)

    def test_a_derivation_hash_that_does_not_match_its_sequence_is_caught(self) -> None:
        receipt = self.base_receipt()
        receipt.derivation.gate_sequence = "G9_INVENTED:pass:"

        result = verify(receipt)

        assert not result.ok
        assert any("derivation" in failure for failure in result.failures)

    def test_an_override_whose_hashes_agree_is_caught(self) -> None:
        """
        A receipt claiming the Membrane substituted a value while showing the
        emission identical to the claim is internally inconsistent — except for
        the prose-only case, which is why the check reads the gate.
        """
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

        result = verify(receipt)

        assert not result.ok
        assert any("override" in failure for failure in result.failures)

    def test_a_prose_only_override_is_not_flagged(self) -> None:
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="DLP_BLOCK",
        )

        assert verify(receipt).ok

    def test_an_emit_whose_hashes_differ_is_caught(self) -> None:
        receipt = mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        result = verify(receipt)

        assert not result.ok
        assert any("emit" in failure for failure in result.failures)

    def test_an_unknown_format_version_is_refused_outright(self) -> None:
        """
        Refusing rather than best-effort checking. A future signed format read by
        this code would have its signature ignored, and reporting `ok` on it is
        the downgrade the version string exists to prevent.
        """
        receipt = self.base_receipt()
        receipt.version = "AURA-RECEIPT-V1"

        result = verify(receipt)

        assert not result.ok
        assert any("version" in failure for failure in result.failures)
