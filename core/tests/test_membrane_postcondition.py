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


def _Safety_with(margin: float) -> _Safety:
    """A settings object identical to `_Safety` but for the margin under test."""
    settings = _Safety()
    settings.min_profit_margin = margin
    return settings


def guarded_membrane(guard: OutputGuard | None = None) -> HiveMembrane:
    """A Membrane over a real guard, optionally one the caller has tampered with."""
    registry = SkillRegistry()
    skill = GuardSkill()
    skill.bind(_Safety(), guard or OutputGuard(safety_settings=_Safety()))
    registry.register(skill.get_name(), skill)
    return HiveMembrane(registry=registry)


def negotiation_context(request_id: str = "", cost: float = COST) -> Context:
    """
    Floor and cost live in metadata, as the Membrane reads them.

    The `hive` oneof is populated because the substitute price keys its jitter
    on `request_id`, and the existing helpers in test_membrane_derivation.py
    build a metadata-only Context where that field does not exist.
    """
    return Context(
        metadata=make_struct({"floor_price": str(FLOOR), "internal_cost": str(cost)}),
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
    async def test_a_dlp_override_that_then_fails_the_postcondition(
        self,
    ) -> None:
        """
        Two regressions on one sequence. DLP fires first here — the message
        leaks `floor_price` — and records `override_scope="prose"`. The guard's
        substitute for the price violation then fails the post-condition
        exactly as in `test_the_override_substitute_is_checked`.

        `override_scope` must not survive the move to UNAVAILABLE: the receipt
        no longer describes an override, so nothing should say "prose".

        And `outcome_gate` must move WITH the outcome. It used to stay
        "DLP_BLOCK" because `record()` was first-wins forever, shipping
        "unavailable because DLP" — which the error table contradicts (a psi
        failure is POSTCONDITION_VIOLATION) and which `verify()` does not catch,
        because it checks no gate/outcome coherence for UNAVAILABLE. First-wins
        holds within an outcome class and resets when the class changes.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        leaking = Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            reasoning="LLM reasoning",
            negotiation=NegotiationIntent(
                price=500.0,
                message="my floor_price is 1000, so I can't go any lower",
            ),
        )
        result = await membrane.inspect_outbound(leaking, negotiation_context())

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert result.receipt.outcome_gate == "POSTCONDITION_VIOLATION"
        assert result.receipt.override_scope == ""

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


class TestFailureRecoveryPricesFromTheSamePremises:
    """
    The recovery path asked for a substitute priced from `floor_price` alone
    and then judged it against `internal_cost` — two different sets of
    premises, one line apart.
    """

    @pytest.mark.asyncio
    async def test_a_cost_above_the_floor_still_recovers(self) -> None:
        """
        floor 1000, cost 1200, m 0.1. Pricing from the floor alone gives
        1111.11, PSI_MIN_MARGIN refuses it (1111.11 x 0.9 = 1000.00 < 1200),
        and the path that exists to keep a broken decision alive emitted
        nothing at all. Silently unrecoverable wherever cost > floor x (1 - m).

        Pre-branch this same input emitted the 1111.11 unjudged, so the bug is
        older than the refusal; what the branch changed is which way it fails.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(action=ActionType.ACTION_TYPE_ERROR, reasoning="model failed"),
            negotiation_context(cost=1200.0),
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.receipt.outcome_gate == "FAILURE_RECOVERY"
        assert decision.action == ActionType.ACTION_TYPE_COUNTER
        # cost / (1 - m) = 1333.33..., rounded up to the cent.
        assert decision.negotiation.price >= 1333.34


class TestTheSanitisedMessageMatchesTheAction:
    @pytest.mark.asyncio
    async def test_an_accept_is_not_rephrased_as_a_counter(self) -> None:
        """
        The DLP block keeps the model's action but used one fixed sentence, so a
        sanitised ACCEPT went out saying "My counter-offer for this item is $X"
        beside an `accepted` result. A message that disagrees with the decision
        printed next to it is its own tell.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_ACCEPT,
                reasoning="LLM reasoning",
                negotiation=NegotiationIntent(
                    price=2000.0, message="my floor_price is 1000"
                ),
            ),
            negotiation_context(),
        )

        assert decision.action == ActionType.ACTION_TYPE_ACCEPT
        assert "counter-offer" not in decision.negotiation.message
        assert "2000.00" in decision.negotiation.message


class TestPsiHoldsOnEveryEmittedPrice:
    """
    The property test `DECISION_RECEIPT.md` §3.8 has always cited and which did
    not exist.

    What existed was `TestTheSubstituteSatisfiesIt`, which fixes floor at 100,
    never varies the proposed price, and calls `calculate_safe_price` directly —
    so "or the decision was refused" was never exercised at all, and neither was
    anything the Membrane does between the guard's answer and the wire.

    The claim under test is the one the whole exercise is for: **either the
    price that left satisfies psi, or nothing left.** Driven through
    `inspect_outbound`, over the five inputs the doc names, including the three
    cases an audit used to break the first draft of the design — cost above
    floor, m at 0.0 and near 1.0, and prices whose exact substitute does not
    land on a cent.

    Seeded rather than random: a failure has to be reproducible from the test
    name alone. Not `hypothesis`, which is not a dependency of this workspace
    and is not worth adding for one property.
    """

    CASES = 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("margin", [0.0, 0.01, 0.1, 0.25, 0.5, 0.9, 0.99])
    async def test_either_psi_holds_or_nothing_was_emitted(self, margin: float) -> None:
        import random

        rng = random.Random(f"psi-property-{margin}")
        engine = OutputGuard(safety_settings=_Safety_with(margin))
        membrane = guarded_membrane(engine)

        for case in range(self.CASES):
            if case % 11 == 0:
                # No usable premise: nothing to price a substitute from, so the
                # only correct answer is to refuse. Included deliberately, or
                # the "or the decision was refused" half of the property is
                # never reached — on well-formed inputs the substitute always
                # satisfies psi, which is the whole guarantee, so the refusal
                # branch is only observable here.
                floor, cost = 0.0, 0.0
                proposed = round(rng.uniform(-500.0, 0.0), 2)
            else:
                floor = round(rng.uniform(0.01, 100_000.0), 2)
                # Deliberately reaches above the floor: where cost >
                # floor x (1 - m) no price derived from the floor alone
                # satisfies psi, and that is the case the audit broke the first
                # design on.
                cost = round(rng.uniform(0.01, floor * 1.5), 2)
                proposed = round(rng.uniform(0.01, floor * 2.0), 2)
            request_id = f"req-{rng.randrange(10**12)}"

            context = Context(
                metadata=make_struct(
                    {"floor_price": str(floor), "internal_cost": str(cost)}
                ),
                hive=HiveContextData(request_id=request_id),
            )

            decision = await membrane.inspect_outbound(
                counter_intent(price=proposed), context
            )

            trace = (
                f"case {case}: floor={floor} cost={cost} m={margin} "
                f"proposed={proposed} request_id={request_id} "
                f"outcome={decision.receipt.outcome} "
                f"gate={decision.receipt.outcome_gate!r}"
            )

            if decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE:
                # Refused. Nothing priced left, and the refusal says so rather
                # than carrying a number a caller could forward.
                assert decision.action == ActionType.ACTION_TYPE_REJECT, trace
                # No price at all, not a price of zero: the refusal carries no
                # number a caller could forward as a real counter-offer.
                assert not decision.negotiation, trace
                continue

            assert decision.negotiation is not None, trace
            emitted = decision.negotiation.price
            held = engine.check_postcondition(
                {"price": emitted},
                {"floor_price": floor, "internal_cost": cost},
            )
            assert held.holds, f"{trace} emitted={emitted} clause={held.failed_clause}"

    @pytest.mark.asyncio
    async def test_the_receipt_of_every_emitted_price_verifies(self) -> None:
        """
        The same grid against `verify()` rather than psi. A receipt the Membrane
        mints and its own verifier refuses is the defect this branch shipped
        with, and one parametrised case caught it — a property over the whole
        input space is what says there is not a second one.
        """
        import random

        from aura_hive.hive.membrane.receipt import verify

        rng = random.Random("psi-property-verify")
        membrane = guarded_membrane()

        for case in range(self.CASES):
            if case % 11 == 0:
                floor, cost = 0.0, 0.0
                proposed = round(rng.uniform(-500.0, 0.0), 2)
            else:
                floor = round(rng.uniform(0.01, 100_000.0), 2)
                cost = round(rng.uniform(0.01, floor * 1.5), 2)
                proposed = round(rng.uniform(0.01, floor * 2.0), 2)
            message = (
                "my floor_price is confidential"
                if case % 3 == 0
                else "here is my offer"
            )

            context = Context(
                metadata=make_struct(
                    {"floor_price": str(floor), "internal_cost": str(cost)}
                ),
                hive=HiveContextData(request_id=f"req-{rng.randrange(10**12)}"),
            )

            intent = counter_intent(price=proposed)
            intent.negotiation.message = message

            decision = await membrane.inspect_outbound(intent, context)
            result = verify(decision.receipt)

            assert result.ok, (
                f"case {case}: floor={floor} cost={cost} proposed={proposed} "
                f"message={message!r} failures={result.failures}"
            )
