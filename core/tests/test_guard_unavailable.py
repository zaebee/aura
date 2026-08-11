"""
`calculate_safe_price` now has a raising path: `GuardUnavailable`, when
neither `floor_price` nor `internal_cost` is a usable positive value (see
test_guard_safe_offer.py's TestGuardUnavailable and
test_guard_gates.py::test_a_null_floor_and_absent_cost_refuses_rather_than_pricing_at_zero
for the engine-level behaviour).

Two call sites in `GuardSkill` reach it: `_get_safe_price`, which calls it
directly, and the `except SafetyViolation` handler in `execute`, which calls
it while already unwinding a different failure. Neither may let the raise
turn into an opaque crash or, worse, a `success=True` Observation — a
GuardUnavailable is exactly the case where nothing was safely established.
"""

from typing import Any

import pytest
from aura_core import SkillRegistry
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


def guard() -> GuardSkill:
    settings = SafetySettings(min_profit_margin=0.1)
    skill = GuardSkill()
    skill.bind(settings, OutputGuard(safety_settings=settings))
    skill.inject_registry(SkillRegistry())
    return skill


def code_of(observation: Any) -> str:
    return str(observation.metadata.to_dict().get("error_code", ""))


class TestGetSafePriceDirectly:
    """The capability that calls calculate_safe_price with nothing upstream of it."""

    @pytest.mark.asyncio
    async def test_an_unusable_context_fails_rather_than_succeeding(self) -> None:
        obs = await guard().execute(
            "get_safe_price",
            {"context": {"floor_price": float("nan"), "internal_cost": None}},
        )

        assert obs.success is False

    @pytest.mark.asyncio
    async def test_it_names_itself_as_the_guard_being_unavailable(self) -> None:
        obs = await guard().execute("get_safe_price", {"context": {}})

        assert code_of(obs) == "GUARD_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_the_cause_is_not_swallowed(self) -> None:
        obs = await guard().execute("get_safe_price", {"context": {}})

        assert "floor_price" in obs.error or "internal_cost" in obs.error

    @pytest.mark.asyncio
    async def test_a_usable_context_still_succeeds(self) -> None:
        """The new failure path must not have narrowed the working one."""
        obs = await guard().execute(
            "get_safe_price",
            {"context": {"floor_price": 100.0, "internal_cost": 100.0}},
        )

        assert obs.success is True
        assert float(obs.metadata.to_dict()["safe_price"]) == 111.12


class TestSafePriceUnavailableInsideAViolationReport:
    """
    `validate_decision` raises SafetyViolation on the first gate that fails,
    and `execute`'s handler for it computes a substitute price to attach to
    the report. When the context behind that decision has no usable
    floor_price or internal_cost either, that inner call now raises too —
    inside a handler that is already unwinding the original violation.
    """

    @pytest.mark.asyncio
    async def test_the_original_violation_still_reports_as_a_failure(self) -> None:
        obs = await guard().execute(
            "validate_decision",
            {
                "decision": {"action": "counter", "price": None},
                "context": {},
            },
        )

        assert obs.success is False
        assert code_of(obs) == "INVALID_PRICE"

    @pytest.mark.asyncio
    async def test_it_does_not_invent_a_zero_safe_price(self) -> None:
        obs = await guard().execute(
            "validate_decision",
            {
                "decision": {"action": "counter", "price": None},
                "context": {},
            },
        )
        meta = obs.metadata.to_dict()

        assert "safe_price" not in meta
        assert meta.get("safe_price_error") == "GUARD_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_the_gate_sequence_still_reaches_the_report(self) -> None:
        """
        The inability to price a substitute must not cost the report the
        derivation it would otherwise carry — that is what names which gate
        refused the decision.
        """
        obs = await guard().execute(
            "validate_decision",
            {
                "decision": {"action": "counter", "price": None},
                "context": {},
            },
        )
        meta = obs.metadata.to_dict()

        assert meta.get("gate_sequence")
        assert meta.get("derivation_hash")

    @pytest.mark.asyncio
    async def test_a_usable_context_still_carries_a_safe_price(self) -> None:
        """The unchanged case: a real floor still prices a substitute as before."""
        obs = await guard().execute(
            "validate_decision",
            {
                "decision": {"action": "counter", "price": 500.0},
                "context": {"floor_price": 1000.0, "internal_cost": 500.0},
            },
        )
        meta = obs.metadata.to_dict()

        assert obs.success is False
        assert "safe_price_error" not in meta
        assert float(meta["safe_price"]) > 0
