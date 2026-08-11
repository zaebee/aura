"""
The guard evaluates the gates its rule set declares, and says which one fired.

Before this, the identity of the rule that refused a decision was recovered
downstream by searching the exception message for "margin" or "floor". That is
fragile in the ordinary way — rewording a message silently relabels an audit
trail — and it was already wrong: the fail-closed branch raises "Cannot validate
margin: safety settings not provided", which matches "margin", so a deployment
that could not read its own settings reported a MIN_MARGIN_VIOLATION.

Gates now carry their code from ruleset.yaml, and the engine walks the declared
order rather than a hand-written if-chain.
"""

import pytest
from aura_hive.hive.proteins.guard.engine import OutputGuard, SafetyViolation
from aura_hive.hive.proteins.guard.ruleset import RulesetError, load_ruleset


class _Safety:
    min_profit_margin = 0.10


def guard(settings: object | None = None) -> OutputGuard:
    return OutputGuard(safety_settings=settings)


def decision(price: float, action: str = "counter") -> dict[str, float | str]:
    return {"action": action, "price": price}


def context(floor: float = 1000.0, cost: float = 500.0) -> dict[str, float]:
    return {"floor_price": floor, "internal_cost": cost}


class TestGateCodes:
    def test_a_violation_carries_the_gates_declared_code(self) -> None:
        with pytest.raises(SafetyViolation) as caught:
            guard(_Safety()).validate_decision(decision(price=500.0), context())

        assert caught.value.code == "FLOOR_PRICE_VIOLATION"

    def test_a_non_positive_price_is_not_a_generic_violation(self) -> None:
        """
        This used to fall through to SAFETY_VIOLATION: the message "Invalid
        offered price" matched neither substring the caller looked for, so a
        malformed price and an unclassified failure were indistinguishable.
        """
        with pytest.raises(SafetyViolation) as caught:
            guard(_Safety()).validate_decision(decision(price=0.0), context())

        assert caught.value.code == "INVALID_PRICE"

    def test_missing_settings_reports_configuration_not_margin(self) -> None:
        """
        The behaviour change worth flagging. A guard that cannot read its
        settings still fails closed — that part is unchanged — but it now says
        so. Reporting SETTINGS_MISSING as a margin violation sent an operator
        looking at pricing when the fault was deployment.
        """
        with pytest.raises(SafetyViolation) as caught:
            guard(settings=None).validate_decision(decision(price=2000.0), context())

        assert caught.value.code == "SETTINGS_MISSING"

    def test_a_thin_margin_reports_the_margin_gate(self) -> None:
        with pytest.raises(SafetyViolation) as caught:
            guard(_Safety()).validate_decision(
                decision(price=1010.0), context(floor=1000.0, cost=1000.0)
            )

        assert caught.value.code == "MIN_MARGIN_VIOLATION"


class TestGateOrder:
    def test_the_floor_gate_fires_before_the_settings_gate(self) -> None:
        """
        Preserves what shipped. A below-floor price on a deployment with no
        settings was refused for the floor, and decisions already in flight
        carry that reason.
        """
        with pytest.raises(SafetyViolation) as caught:
            guard(settings=None).validate_decision(decision(price=500.0), context())

        assert caught.value.code == "FLOOR_PRICE_VIOLATION"

    def test_the_price_gate_fires_before_the_floor_gate(self) -> None:
        with pytest.raises(SafetyViolation) as caught:
            guard(_Safety()).validate_decision(decision(price=-5.0), context())

        assert caught.value.code == "INVALID_PRICE"

    def test_a_clean_decision_passes_every_gate(self) -> None:
        assert guard(_Safety()).validate_decision(decision(price=2000.0), context())

    def test_an_action_outside_scope_is_not_judged(self) -> None:
        """
        Only accept and counter put a price on the wire, so only those are
        judged. A reject carrying a nonsense price is not a safety failure.
        """
        assert guard(_Safety()).validate_decision(
            decision(price=-5.0, action="reject"), context()
        )


class TestDeclarationMatchesImplementation:
    def test_the_engine_implements_exactly_the_declared_gates(self) -> None:
        """
        The cross-check that keeps the version string honest. A gate declared
        but not implemented never fires while the rule set says it does; one
        implemented but not declared runs outside anything a receipt records.
        """
        load_ruleset().validate_against(
            set(OutputGuard.gate_ids()), set(OutputGuard.clause_ids())
        )

    def test_an_engine_missing_a_declared_gate_is_rejected(self) -> None:
        with pytest.raises(RulesetError, match="G4_MARGIN_VIOLATION"):
            load_ruleset().validate_against(
                set(OutputGuard.gate_ids()) - {"G4_MARGIN_VIOLATION"},
                set(OutputGuard.clause_ids()),
            )


class TestSafePriceStrategy:
    def test_the_reason_no_longer_selects_a_formula(self) -> None:
        """
        The strategy is declared once for the set now (ruleset.yaml
        `safe_price: safe_offer`), not per gate, so which gate fired no longer
        changes which formula prices the substitute. Transitional: this is the
        old `margin` formula standing in for every reason until Task 3 replaces
        it with the real `safe_offer` computation.
        """
        engine = guard(_Safety())

        margin_price = engine.calculate_safe_price(context(), "MIN_MARGIN_VIOLATION")
        markup_price = engine.calculate_safe_price(context(), "FLOOR_PRICE_VIOLATION")

        assert margin_price == markup_price

    def test_missing_settings_gets_the_same_formula(self) -> None:
        """
        Every reason prices the same way now that the strategy is set-wide, so
        a misconfigured deployment does not answer with a cheaper number by
        virtue of which gate happened to fire.
        """
        engine = guard(_Safety())

        assert engine.calculate_safe_price(
            context(), "SETTINGS_MISSING"
        ) == engine.calculate_safe_price(context(), "MIN_MARGIN_VIOLATION")

    def test_an_unrecognised_reason_still_yields_a_price(self) -> None:
        """
        Callers pass reasons the rule set does not name — FAILURE_RECOVERY comes
        from the Membrane, not from a gate — and those still need a price. There
        is one formula now, so an unrecognised reason gets the same answer as
        every other.
        """
        assert guard(_Safety()).calculate_safe_price(
            context(), "FAILURE_RECOVERY"
        ) == pytest.approx(1111.11)


class TestSafePriceNeverUndercutsTheFloor:
    """
    The substitute price exists to be safe, so producing one below the floor is
    the one outcome it must never have.

    `min_profit_margin` is env-configurable and carries no `ge=0` bound, so a
    negative value is an operator typo away: floor/(1-(-0.5)) is floor/1.5, and
    a floor of 1000 came back as 666.67. The old guard only rejected margins at
    or above 1.0, which catches the undefined case and misses this one.
    """

    @pytest.mark.parametrize("margin", [-0.5, -0.01, 1.0, 1.5])
    def test_a_margin_outside_the_valid_range_never_prices_below_the_floor(
        self, margin: float
    ) -> None:
        class _Configured:
            min_profit_margin = margin

        price = guard(_Configured()).calculate_safe_price(
            context(), "MIN_MARGIN_VIOLATION"
        )

        assert price >= 1000.0

    def test_a_margin_that_is_not_a_number_still_yields_a_price(self) -> None:
        """
        Reached without a gate having run: the Membrane calls this directly on
        FAILURE_RECOVERY, so a bad setting cannot be assumed already caught.
        """

        class _Broken:
            min_profit_margin = None

        price = guard(_Broken()).calculate_safe_price(context(), "SETTINGS_MISSING")

        assert price >= 1000.0

    def test_a_valid_margin_is_still_honoured(self) -> None:
        """The clamp must not flatten every deployment onto the default."""

        class _Configured:
            min_profit_margin = 0.50

        assert guard(_Configured()).calculate_safe_price(
            context(), "MIN_MARGIN_VIOLATION"
        ) == pytest.approx(2000.0)


class TestUnusableInputsStillNameAGate:
    """
    A null or unparseable number must not cost the decision its gate.

    Nothing crashes today: the predicate raises TypeError, `skill.py` catches it
    into a generic Observation, and `SkillRegistry.execute` would catch it even
    if that did not. But the Observation carries no `error_code`, so the Membrane
    falls back to SAFETY_VIOLATION and the audit trail stops naming which rule
    refused the decision — which is the whole point of the gate codes.

    Unreachable from the Membrane, which coerces every value to float before the
    guard sees it. Reachable from `guard__validate_safety`, declared as an LLM
    tool in manifest.yaml, where a model emitting `"price": null` is ordinary.
    """

    @pytest.mark.parametrize("price", [None, "not a number"])
    def test_an_unusable_price_is_an_invalid_price(self, price: object) -> None:
        with pytest.raises(SafetyViolation) as caught:
            guard(_Safety()).validate_decision(
                {"action": "counter", "price": price}, context()
            )

        assert caught.value.code == "INVALID_PRICE"

    def test_an_unusable_floor_is_treated_as_an_absent_one(self) -> None:
        """
        Matches what a missing key already does rather than inventing a stricter
        rule here: `floor_price` defaults to 0.0 throughout, so a null reads the
        same as no floor supplied. That default is permissive, and deliberately
        left alone — see the note on #258.
        """
        assert guard(_Safety()).validate_decision(
            {"action": "counter", "price": 2000.0},
            {"floor_price": None, "internal_cost": 500.0},
        )

    def test_an_unusable_cost_is_judged_rather_than_exploding(self) -> None:
        """
        Cost reads as 0.0, so the margin computes to 1.0 and G4 passes. The
        property under test is that the gate reached a verdict at all: before,
        the comparison raised past every gate and the decision came back with no
        code attached.
        """
        assert guard(_Safety()).validate_decision(
            {"action": "counter", "price": 1000.0},
            {"floor_price": 1000.0, "internal_cost": "unknown"},
        )

    def test_a_null_floor_still_yields_a_safe_price(self) -> None:
        """
        Reached from inside `skill.py`'s SafetyViolation handler, which is a
        sibling of its generic `except Exception` rather than nested inside it.
        A raise here escapes the skill entirely.
        """
        assert guard(_Safety()).calculate_safe_price(
            {"floor_price": None}, "FLOOR_PRICE_VIOLATION"
        ) == pytest.approx(0.0)


class TestFailClosedOnIncompleteSettings:
    def test_a_settings_object_without_the_margin_is_misconfiguration(self) -> None:
        """
        G3 exists to catch a deployment that cannot read its own settings, and
        "present but incomplete" is that case. Before, only `settings is None`
        counted, so an object missing the field slipped through to G4 and raised
        AttributeError — which the skill swallowed into a generic
        SAFETY_VIOLATION, losing the fail-closed reason the gate was for.
        """

        class _Incomplete:
            pass

        with pytest.raises(SafetyViolation) as caught:
            guard(_Incomplete()).validate_decision(decision(price=2000.0), context())

        assert caught.value.code == "SETTINGS_MISSING"

    def test_a_settings_object_with_a_null_margin_is_misconfiguration(self) -> None:
        class _Null:
            min_profit_margin = None

        with pytest.raises(SafetyViolation) as caught:
            guard(_Null()).validate_decision(decision(price=2000.0), context())

        assert caught.value.code == "SETTINGS_MISSING"
