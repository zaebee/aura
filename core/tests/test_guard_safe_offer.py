"""
The substitute price, and the two ways the arithmetic used to betray it.

`round(floor/(1-m), 2)` rounds toward the nearest cent, which for a margin
substitute means half the time toward breaching it, and a lower price is a lower
margin. And the substitute was a function of `floor` alone while the margin rule
is about `internal_cost`, so where cost exceeded floor no substitute could
satisfy it at all. Both produced prices the guard's own post-condition rejects.
"""

from decimal import Decimal

import pytest
from aura_hive.hive.proteins.guard.engine import (
    GuardUnavailable,
    OutputGuard,
    SafetyViolation,
)


class Settings:
    def __init__(self, margin: float = 0.1) -> None:
        self.min_profit_margin = margin


def holds(price: float, floor: float, cost: float, margin: float) -> bool:
    """psi, in Decimal, exactly as the rule set declares it."""
    p, c, m = Decimal(str(price)), Decimal(str(cost)), Decimal(str(margin))
    return p > 0 and p >= Decimal(str(floor)) and p * (1 - m) >= c


class TestRounding:
    def test_the_default_configuration_satisfies_the_margin_rule(self) -> None:
        """
        floor=100, cost=100, m=0.1 requires 111.1111..., and rounding to the
        nearest cent gave 111.11 — margin 0.099991, under the minimum. This is
        the case the audit broke the first design on.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": 100.0}
        )
        assert price == 111.12
        assert holds(price, 100.0, 100.0, 0.1)

    @pytest.mark.parametrize(
        "margin", [0.0, 0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.75, 0.99]
    )
    def test_every_admissible_margin_satisfies_the_rule(self, margin: float) -> None:
        guard = OutputGuard(safety_settings=Settings(margin))
        price = guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": 100.0}
        )
        assert holds(price, 100.0, 100.0, margin)


class TestCostAboveFloor:
    def test_a_cost_above_the_floor_still_yields_a_satisfying_price(self) -> None:
        """
        The substitute used to read only `floor`, so at cost > floor it produced
        a price the margin rule rejects — the guard refusing its own safe offer.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": 120.0}
        )
        assert holds(price, 100.0, 120.0, 0.1)
        assert price >= 120.0


class TestNonFinite:
    """
    NaN and +/-Infinity are legal `double` wire values — floor_price and
    internal_cost arrive over protobuf, and min_profit_margin is
    env-configurable, where `float("nan")` parses without error. The old
    float-comparison code degraded a non-finite margin to _DEFAULT_MARGIN for
    free (`0.0 <= nan < 1.0` is False); `decimal.Decimal`'s comparison raises
    InvalidOperation on NaN instead, so the rewrite needs its own explicit
    handling for all three inputs, and must never raise.

    A non-finite margin falls back to _DEFAULT_MARGIN (0.1), matching the
    settings-missing path. A non-finite floor_price or internal_cost is read
    as 0 — the same fallback already used for a value that was never sent
    (see TestCostAboveFloor and the null-floor case in
    test_guard_gates.py) — since it appears only inside `max(...)`, a 0 can
    only be outweighed by the other, trustworthy input, never pull the price
    below what that input alone requires.
    """

    @pytest.mark.parametrize("margin", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_margin_falls_back_to_the_default(self, margin: float) -> None:
        guard = OutputGuard(safety_settings=Settings(margin))
        price = guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": 100.0}
        )
        assert price == 111.12
        assert holds(price, 100.0, 100.0, 0.1)

    @pytest.mark.parametrize("floor", [float("nan"), float("inf")])
    def test_a_non_finite_floor_does_not_raise_and_still_satisfies_the_rule(
        self, floor: float
    ) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price(
            {"floor_price": floor, "internal_cost": 100.0}
        )
        # floor_price is read as 0 (see class docstring), so the margin term
        # on internal_cost is what the price is checked against.
        assert holds(price, 0.0, 100.0, 0.1)

    @pytest.mark.parametrize("cost", [float("nan"), float("inf")])
    def test_a_non_finite_cost_does_not_raise_and_still_satisfies_the_rule(
        self, cost: float
    ) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": cost}
        )
        # internal_cost is read as 0 (see class docstring), so the price is
        # checked against the floor alone.
        assert holds(price, 100.0, 0.0, 0.1)

    def test_a_floor_price_at_the_default_context_overflow_does_not_raise(
        self,
    ) -> None:
        """
        The default 28-digit Decimal context raises InvalidOperation when
        quantize is asked to round a value that needs more digits than that
        to represent at the cent — which a floor_price of 1e28 does. Widened
        locally in calculate_safe_price; this is that widening's regression
        test.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price({"floor_price": 1e28, "internal_cost": 0.0})
        assert price > 0
        assert price >= 1e28
        assert holds(price, 1e28, 0.0, 0.1)


class TestGuardUnavailable:
    """
    A non-finite or absent `floor_price` and `internal_cost` degrade to
    Decimal(0) individually (see TestNonFinite), and a 0 that stands beside a
    real, positive counterpart can only ever be outweighed inside `max(...)`.

    That argument needs a trustworthy counterpart to lean on. When BOTH
    degrade the same way — nan/nan, inf/inf, nan/inf, -inf/-inf, or neither
    key sent at all — there is no positive input left anywhere in the
    formula, and the old code returned `0.0`: a price that fails the guard's
    own G1_PRICE_POSITIVE gate and psi's `price > 0`, silently. This class
    is the fix: refuse instead of inventing a number nothing justifies.
    """

    @pytest.mark.parametrize(
        "context",
        [
            pytest.param(
                {"floor_price": float("nan"), "internal_cost": float("nan")},
                id="nan/nan",
            ),
            pytest.param(
                {"floor_price": float("inf"), "internal_cost": float("inf")},
                id="inf/inf",
            ),
            pytest.param(
                {"floor_price": float("nan"), "internal_cost": float("inf")},
                id="nan/inf",
            ),
            pytest.param(
                {"floor_price": float("-inf"), "internal_cost": float("-inf")},
                id="-inf/-inf",
            ),
            pytest.param({}, id="absent/absent"),
        ],
    )
    def test_neither_input_usable_refuses(self, context: dict) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        with pytest.raises(GuardUnavailable):
            guard.calculate_safe_price(context)

    def test_it_is_not_a_safety_violation(self) -> None:
        """
        A judgment that never happened is not a rule judging against a
        decision. A caller that means to catch one must not accidentally
        catch the other by inheritance.
        """
        assert not issubclass(GuardUnavailable, SafetyViolation)
        assert not issubclass(SafetyViolation, GuardUnavailable)

    def test_one_usable_input_still_prices_as_before(self) -> None:
        """
        The property this class must not break: a lone trustworthy floor or
        cost is still enough to price a substitute, unchanged from
        TestCostAboveFloor and TestNonFinite.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))

        assert (
            guard.calculate_safe_price({"floor_price": 100.0, "internal_cost": 100.0})
            == 111.12
        )
        # floor unusable, cost=100.0 usable: floor reads as 0, so the price
        # is set entirely by the margin term on cost — same 111.12 as above.
        assert guard.calculate_safe_price(
            {"floor_price": float("nan"), "internal_cost": 100.0}
        ) == pytest.approx(111.12)
        # cost unusable, floor=100.0 usable: cost reads as 0, so the margin
        # term (100/0.9) still exceeds the 1.05x markup term — same 111.12.
        assert guard.calculate_safe_price(
            {"floor_price": 100.0, "internal_cost": float("nan")}
        ) == pytest.approx(111.12)


class TestJitter:
    def test_the_price_is_stable_within_one_session(self) -> None:
        """
        Redrawing per decision would let a counterparty average the noise away
        over rounds. Keyed on request_id, it cannot.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        prices = {
            guard.calculate_safe_price(ctx, request_id="sess-abc") for _ in range(5)
        }
        assert len(prices) == 1

    def test_the_price_differs_across_sessions(self) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        prices = {
            guard.calculate_safe_price(ctx, request_id=f"sess-{n}") for n in range(20)
        }
        assert len(prices) > 1

    def test_jitter_never_lowers_the_price(self) -> None:
        """
        psi survives jitter only because (1 + j) >= 1 and the rounding is a
        ceiling. A jitter that could subtract would reintroduce the whole bug.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        base = guard.calculate_safe_price(ctx)
        for n in range(50):
            assert guard.calculate_safe_price(ctx, request_id=f"s-{n}") >= base

    def test_every_jitter_draw_satisfies_the_rule(self) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        for n in range(200):
            floor, cost = 100.0 + n, 90.0 + n
            price = guard.calculate_safe_price(
                {"floor_price": floor, "internal_cost": cost}, request_id=f"s-{n}"
            )
            assert holds(price, floor, cost, 0.1)
