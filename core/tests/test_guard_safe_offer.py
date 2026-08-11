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
from aura_hive.hive.proteins.guard.engine import OutputGuard


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
