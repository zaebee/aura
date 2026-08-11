"""
The guard records how it reached its verdict, not just what the verdict was.

`outcome_gate` names the rule that refused a decision. It does not say which
rules were consulted first, so it cannot be replayed: two deployments could
report the same failing gate having evaluated entirely different sets on the way
there. The gate sequence is that record — every gate that ran, in order, with its
verdict — and `derivation_hash` is a digest over it (docs/DECISION_RECEIPT.md
§3.4).

The property that makes the record safe to hand to a counterparty is that it
names premise *keys* and never their values. `G2_FLOOR_VIOLATION:fail:price,
floor_price` says the floor was consulted; it does not say what the floor is.
Recording values here would hand over exactly what the DLP gate exists to
protect, and it would do it in a field designed to be published.
"""

import pytest
from aura_hive.hive.proteins.guard.engine import OutputGuard, SafetyViolation

FLOOR = 1000.0


class _Safety:
    min_profit_margin = 0.10


def guard(settings: object | None = None) -> OutputGuard:
    return OutputGuard(safety_settings=settings if settings is not None else _Safety())


def decision(price: float, action: str = "counter") -> dict[str, object]:
    return {"action": action, "price": price}


def context(floor: float = FLOOR, cost: float = 500.0) -> dict[str, float]:
    return {"floor_price": floor, "internal_cost": cost}


class TestTheRecordedSequence:
    def test_a_clean_decision_records_every_gate_as_passed(self) -> None:
        derivation = guard().evaluate(decision(price=2000.0), context())

        assert derivation.canonical == (
            "G1_PRICE_POSITIVE:pass:price\x1f"
            "G2_FLOOR_VIOLATION:pass:price,floor_price\x1f"
            "G3_SETTINGS_PRESENT:pass:\x1f"
            "G4_MARGIN_VIOLATION:pass:price,internal_cost"
        )

    def test_the_sequence_stops_at_the_gate_that_failed(self) -> None:
        """
        Short-circuiting is visible in the record rather than hidden by it: the
        sequence ends at the failure because evaluation did, and a verifier can
        see that G3 and G4 were never consulted.
        """
        derivation = guard().evaluate(decision(price=500.0), context())

        assert derivation.canonical == (
            "G1_PRICE_POSITIVE:pass:price\x1fG2_FLOOR_VIOLATION:fail:price,floor_price"
        )
        assert derivation.failed_gate == "G2_FLOOR_VIOLATION"

    def test_the_gates_are_recorded_in_the_rule_sets_order(self) -> None:
        derivation = guard().evaluate(decision(price=2000.0), context())

        assert [record.gate_id for record in derivation.records] == [
            "G1_PRICE_POSITIVE",
            "G2_FLOOR_VIOLATION",
            "G3_SETTINGS_PRESENT",
            "G4_MARGIN_VIOLATION",
        ]

    def test_a_gate_consuming_nothing_records_an_empty_field(self) -> None:
        """
        Not a placeholder character. The draft used an em dash, which is exactly
        the sort of decorative Unicode a canonical form has to normalise away
        before hashing — an empty field needs no normalising.
        """
        derivation = guard().evaluate(decision(price=2000.0), context())
        settings_gate = next(
            r for r in derivation.records if r.gate_id == "G3_SETTINGS_PRESENT"
        )

        assert settings_gate.consumes == ()
        assert "G3_SETTINGS_PRESENT:pass:" in derivation.canonical


class TestTheRecordNeverCarriesAValue:
    """
    The whole record is meant to be publishable. If a value can be read out of
    it, publishing a receipt undoes the Hidden Knowledge invariant the Membrane
    spends its outbound path enforcing.
    """

    @pytest.mark.parametrize("price", [500.0, 2000.0])
    def test_no_number_from_the_inputs_appears_in_the_sequence(
        self, price: float
    ) -> None:
        derivation = guard().evaluate(
            decision(price=price), context(floor=FLOOR, cost=777.0)
        )

        for secret in ("1000", "777", str(price), str(int(price))):
            assert secret not in derivation.canonical

    def test_two_decisions_differing_only_in_value_derive_identically(self) -> None:
        """
        The consequence, stated as a property: the derivation digest is over the
        steps taken, not the numbers they were taken on. Distinguishing those two
        prices is the emission digest's job (§3.6), and keeping it out of this
        field is what stops the digest from being a value oracle.
        """
        cheap = guard().evaluate(decision(price=1500.0), context())
        dear = guard().evaluate(decision(price=9999.0), context())

        assert cheap.digest == dear.digest


class TestByteStability:
    def test_the_same_inputs_derive_byte_identically_across_engines(self) -> None:
        """
        Two fresh engines, because a digest that depends on process state cannot
        be re-derived by anyone else — which is the only thing it is for.
        """
        first = guard().evaluate(decision(price=500.0), context())
        second = guard().evaluate(decision(price=500.0), context())

        assert first.canonical == second.canonical
        assert first.digest == second.digest

    def test_a_different_outcome_derives_differently(self) -> None:
        passed = guard().evaluate(decision(price=2000.0), context())
        failed = guard().evaluate(decision(price=500.0), context())

        assert passed.digest != failed.digest

    def test_the_digest_is_a_full_sha256(self) -> None:
        digest = guard().evaluate(decision(price=2000.0), context()).digest

        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)

    def test_the_digest_is_over_the_recorded_sequence(self) -> None:
        """A verifier confirms the two agree before paying to replay the steps."""
        import hashlib

        derivation = guard().evaluate(decision(price=500.0), context())

        assert (
            derivation.digest
            == hashlib.sha256(derivation.canonical.encode("utf-8")).hexdigest()
        )


class TestNothingDerivedIsNotAnEmptyDerivation:
    def test_an_action_outside_scope_records_no_gates(self) -> None:
        """
        No declared gate ran, so there is nothing to replay. Hashing the empty
        string here would assert a derivation that never happened — the receipt
        would carry a digest a verifier could reproduce and learn nothing from.
        """
        derivation = guard().evaluate(decision(price=-5.0, action="reject"), context())

        assert derivation.records == ()
        assert derivation.canonical == ""
        assert derivation.digest == ""


class TestValidateDecisionStillBehaves:
    """The raising contract is unchanged; `evaluate` is the addition beneath it."""

    def test_a_clean_decision_still_returns_true(self) -> None:
        assert guard().validate_decision(decision(price=2000.0), context())

    def test_a_violation_still_raises_with_its_code(self) -> None:
        with pytest.raises(SafetyViolation) as caught:
            guard().validate_decision(decision(price=500.0), context())

        assert caught.value.code == "FLOOR_PRICE_VIOLATION"

    def test_the_violation_carries_the_derivation_that_produced_it(self) -> None:
        """
        The failure path needs the record too, and it is the path that raises —
        so the derivation travels on the exception rather than being recomputed
        by whoever catches it.
        """
        with pytest.raises(SafetyViolation) as caught:
            guard().validate_decision(decision(price=500.0), context())

        assert caught.value.derivation is not None
        assert caught.value.derivation.failed_gate == "G2_FLOOR_VIOLATION"
