"""
The post-condition, checked where the value actually leaves.

Gates judge the model's proposal. Before this, nothing judged the Membrane's
substitute, so a below-margin override shipped under a receipt that verified.
"""

import pytest
from aura_core import SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    HiveContextData,
    Intent,
    NegotiationIntent,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.proteins.guard.engine import OutputGuard
from aura_hive.hive.proteins.guard.skill import GuardSkill

FLOOR = 1000.0
COST = 777.0


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


def guarded_membrane(guard: OutputGuard | None = None) -> HiveMembrane:
    """A Membrane over a real guard, optionally one the caller has tampered with."""
    registry = SkillRegistry()
    skill = GuardSkill()
    skill.bind(_Safety(), guard or OutputGuard(safety_settings=_Safety()))
    registry.register(skill.get_name(), skill)
    return HiveMembrane(registry=registry)


def negotiation_context(request_id: str = "") -> Context:
    """
    Floor and cost live in metadata, as the Membrane reads them.

    The `hive` oneof is populated because the substitute price keys its jitter
    on `request_id`, and the existing helpers in test_membrane_derivation.py
    build a metadata-only Context where that field does not exist.
    """
    return Context(
        metadata=make_struct({"floor_price": str(FLOOR), "internal_cost": str(COST)}),
        hive=HiveContextData(request_id=request_id),
    )


def counter_intent(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


class TestBothPaths:
    @pytest.mark.asyncio
    async def test_a_passing_decision_is_checked_too(self) -> None:
        """
        Checking only the override path would miss a broken gate on the pass
        path: a predicate stubbed to True lets a bad proposal through untouched,
        and psi is the only thing left that would notice.

        900.0 is chosen, not an arbitrarily low price, because it has to clear
        G4_MARGIN_VIOLATION for real: (900-777)/900 = 0.137 >= 0.10. Only
        G2_FLOOR_VIOLATION is stubbed away, so this is the one price where every
        *evaluated* gate genuinely passes and `validate_decision` succeeds —
        landing on the pass path rather than the override path — while still
        sitting below the floor of 1000, which is what PSI_ABOVE_FLOOR catches.
        A lower price (e.g. 1.0) also fails G4 on its own merits, which would
        route through the override path instead and prove nothing about the
        pass path.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard._gate_floor_violation = lambda decision, context: True  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=900.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert result.receipt.outcome_gate == "POSTCONDITION_VIOLATION"

    @pytest.mark.asyncio
    async def test_the_override_substitute_is_checked(self) -> None:
        """
        The regression for the found bug. A substitute that breaches the margin
        rule must not leave, even though the gates were right to stop the
        proposal that caused it. 1050.00 is floor * 1.05 — what the old strategy
        produced, and 0.26 below the margin rule at a cost of 777.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert result.action == ActionType.ACTION_TYPE_REJECT

    @pytest.mark.asyncio
    async def test_a_satisfying_override_still_emits(self) -> None:
        membrane = guarded_membrane()

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert result.negotiation.price >= 1111.12


class TestNothingLeaks:
    @pytest.mark.asyncio
    async def test_the_offending_price_never_reaches_the_emission(self) -> None:
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert "800" not in str(result.to_dict())
