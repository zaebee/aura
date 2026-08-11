"""
What the guard guarantees about the value it lets out.

The gates judge what the model proposed. Nothing judged what the Membrane
substituted, and that gap is how a price below the minimum margin shipped under
a receipt that verified: G2 fired on the proposal, short-circuited G4, and the
substitute was emitted unexamined.
"""

import pytest
from aura_hive.hive.proteins.guard.engine import (
    GuardUnavailable,
    OutputGuard,
    SafetyViolation,
)


class Settings:
    def __init__(self, margin: float = 0.1) -> None:
        self.min_profit_margin = margin


CONTEXT = {"floor_price": 100.0, "internal_cost": 100.0}


class TestClauses:
    def test_a_satisfying_price_holds(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 111.12}, CONTEXT)
        assert result.holds
        assert result.failed_clause is None

    def test_a_non_positive_price_names_its_clause(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 0.0}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_PRICE_POSITIVE"

    def test_a_price_below_the_floor_names_its_clause(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 99.99}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_ABOVE_FLOOR"

    def test_a_price_below_the_margin_names_its_clause(self) -> None:
        """
        105.00 is above the floor and was what the old floor-markup substitute
        emitted. It breaches the margin rule, and nothing caught it.
        """
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 105.0}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_MIN_MARGIN"

    def test_clauses_are_reported_in_declared_order(self) -> None:
        """
        A price failing two clauses reports the first, so the reason a decision
        was stopped does not depend on evaluation accidents.
        """
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": -5.0}, CONTEXT)
        assert result.failed_clause == "PSI_PRICE_POSITIVE"


class TestTheSubstituteSatisfiesIt:
    @pytest.mark.parametrize("margin", [0.0, 0.05, 0.1, 0.2, 0.33, 0.5, 0.9])
    @pytest.mark.parametrize("cost", [10.0, 99.99, 100.0, 100.01, 250.0])
    def test_the_guards_own_substitute_always_holds(
        self, margin: float, cost: float
    ) -> None:
        """
        The regression for the whole exercise. If this ever fails, the guard is
        refusing the price it computed as safe.
        """
        guard = OutputGuard(safety_settings=Settings(margin))
        context = {"floor_price": 100.0, "internal_cost": cost}
        for n in range(10):
            price = guard.calculate_safe_price(context, request_id=f"s-{n}")
            assert guard.check_postcondition({"price": price}, context).holds


class TestUnavailableIsNotAViolation:
    def test_guard_unavailable_is_not_a_safety_violation(self) -> None:
        """
        A question the guard could not answer is not a rule it answered against.
        A caller catching one must not silently catch the other.
        """
        assert not issubclass(GuardUnavailable, SafetyViolation)
        assert not issubclass(SafetyViolation, GuardUnavailable)

    def test_it_carries_a_code(self) -> None:
        error = GuardUnavailable(
            "persistence is down", code="SANCTIFICATION_UNAVAILABLE"
        )
        assert error.code == "SANCTIFICATION_UNAVAILABLE"
