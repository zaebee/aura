"""
The Membrane counts its own interventions.

Until this existed there was no way to ask how often free reasoning landed
somewhere the guarantee had to catch — the override rewrote the Intent and left
nothing behind but a string in a reasoning field. That rate is the number worth
watching: a membrane that never fires is either perfectly redundant or silently
broken, and without a counter you cannot tell which.
"""

from typing import Any
from unittest.mock import patch

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import ActionType, Context, Intent, NegotiationIntent
from aura_hive.hive.membrane.main import (
    HiveMembrane,
    membrane_interventions_total,
)
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


class _Safety:
    """Minimal stand-in for SafetySettings; the guard reads only these."""

    min_profit_margin = 0.10
    ui_trigger_price = 1000.0
    trade_risk_threshold = 0.10


def guarded_membrane() -> HiveMembrane:
    """
    A Membrane wired the way cortex wires it.

    Worth stating plainly: `inspect_outbound` begins with
    `if not self.registry: return decision`, so an unwired Membrane passes every
    price through untouched. A test that forgets the registry tests nothing.
    """
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    return HiveMembrane(registry=registry)


def count(direction: str, reason: str) -> float:
    """Current value of one labelled series, 0.0 before it has ever fired."""
    value = membrane_interventions_total.labels(
        direction=direction, reason=reason
    )._value.get()
    return float(value)


def negotiation_context(floor_price: float = 1000.0) -> Context:
    return Context(metadata=make_struct({"floor_price": str(floor_price)}))


def counter_intent(price: float, message: str = "Here is my offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message=message),
    )


class TestInbound:
    @pytest.mark.asyncio
    async def test_a_negative_bid_is_counted(self) -> None:
        before = count("inbound", "INVALID_BID")
        membrane = HiveMembrane()

        class Signal:
            bid_amount = -1.0

        with pytest.raises(ValueError):
            await membrane.inspect_inbound(Signal())

        assert count("inbound", "INVALID_BID") == before + 1

    @pytest.mark.asyncio
    async def test_a_clean_signal_counts_nothing(self) -> None:
        before = count("inbound", "INVALID_BID")
        membrane = HiveMembrane()

        class Signal:
            bid_amount = 500.0

        await membrane.inspect_inbound(Signal())
        assert count("inbound", "INVALID_BID") == before


class TestOutbound:
    @pytest.mark.asyncio
    async def test_a_price_below_floor_is_counted(self) -> None:
        """The reason label carries the guard's own code, not a generic string."""
        membrane = guarded_membrane()
        before = count("outbound", "FLOOR_PRICE_VIOLATION")

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context(floor_price=1000.0)
        )

        # The guard's own error_code, not a generic bucket: an operator wants to
        # know which invariant fired, not merely that one did.
        assert count("outbound", "FLOOR_PRICE_VIOLATION") == before + 1
        assert "Membrane Override" in decision.reasoning

    @pytest.mark.asyncio
    async def test_a_price_above_floor_counts_nothing(self) -> None:
        membrane = guarded_membrane()
        before = count("outbound", "FLOOR_PRICE_VIOLATION")

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context(floor_price=1000.0)
        )

        assert count("outbound", "FLOOR_PRICE_VIOLATION") == before
        assert "Membrane Override" not in decision.reasoning

    @pytest.mark.asyncio
    async def test_a_leaked_floor_price_is_counted_separately(self) -> None:
        """DLP rewrites the message in place; it never went through the override."""
        membrane = guarded_membrane()
        before = count("outbound", "DLP_BLOCK")

        await membrane.inspect_outbound(
            counter_intent(price=2000.0, message="our floor_price is 1000"),
            negotiation_context(floor_price=1000.0),
        )

        assert count("outbound", "DLP_BLOCK") == before + 1


class TestFailSafe:
    @pytest.mark.asyncio
    async def test_a_broken_metric_does_not_take_the_guard_down(self) -> None:
        """
        Accounting must never cost a guarantee.

        The decision this call accompanies has already been made. Losing a count
        degrades observability; raising here would lose the negotiation, which is
        strictly worse and buys no safety.
        """
        membrane = guarded_membrane()

        with patch("aura_hive.hive.membrane.main.membrane_interventions_total") as m:
            m.labels.side_effect = RuntimeError("registry corrupted")
            decision = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context(floor_price=1000.0)
            )

        assert "Membrane Override" in decision.reasoning
        # ceil(1000 / (1 - 0.1), cent): the guard's safe_offer substitute price,
        # with no request_id so no jitter is applied here.
        assert decision.negotiation.price == pytest.approx(1111.12)


class TestSeriesShape:
    def test_direction_and_reason_are_separate_labels(self) -> None:
        """Aggregating by reason alone would merge an inbound and outbound rate."""
        sample: Any = membrane_interventions_total.collect()[0].samples[0]
        assert set(sample.labels) == {"direction", "reason"}

    def test_registering_twice_reuses_the_same_collector(self) -> None:
        """Tests import this module repeatedly; a duplicate name would raise."""
        from aura_hive.hive.membrane.main import _get_counter

        again = _get_counter(
            "membrane_interventions_total", "ignored", ["direction", "reason"]
        )
        assert again is membrane_interventions_total

    def test_the_same_name_with_different_labels_raises(self) -> None:
        """Otherwise the mismatch surfaces inside .labels(), far from its cause."""
        from aura_hive.hive.membrane.main import _get_counter

        with pytest.raises(ValueError, match="already registered with labels"):
            _get_counter("membrane_interventions_total", "ignored", ["something_else"])
