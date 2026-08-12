"""
The post-condition, checked where the value actually leaves.

Gates judge the model's proposal. Before this, nothing judged the Membrane's
substitute, so a below-margin override shipped under a receipt that verified.
"""

import random

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


def _proposal(rng: "random.Random", floor: float, case: int) -> float:
    """
    A proposed price, one in three of them finer than a cent.

    Both grids below generated `round(uniform(...), 2)` exclusively, which is
    the one precision class that cannot produce the claim/emission digest
    collision — the digest renders at `.2f`, so a proposal already on a cent
    can never round onto its own substitute. The grids therefore could not
    reach the defect `TestAProposalFinerThanACent` pins, and did not.
    """
    raw = rng.uniform(0.01, floor * 2.0)
    return raw if case % 3 == 1 else round(raw, 2)


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
        """
        The refused substitute must not survive anywhere on the Intent that
        leaves — not in the price, not in the prose, not in the metadata the
        override path writes about what it replaced.

        Searched over the emission with its opaque identifiers removed:
        `decision_id`, `dispute_token` and the digests are uniform, so "800"
        turns up in one of them about 1.5% of the time. A substring search that
        fails at that rate cannot tell a leak from a coincidence, and it was
        failing on the coincidences.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        rendered = result.to_dict()
        rendered.pop("identifier", None)
        rendered.pop("disputeToken", None)
        rendered.pop("receipt", None)

        assert "800" not in str(rendered)
        # The receipt separately, by the fields that could carry a value at all.
        receipt = result.receipt
        assert "800" not in receipt.outcome_gate
        assert "800" not in receipt.override_scope
        assert "800" not in receipt.derivation.gate_sequence


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
                proposed = _proposal(rng, floor, case)
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
                proposed = _proposal(rng, floor, case)
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


class TestAProposalFinerThanACent:
    """
    The digest is taken at cent precision; the gates decide at full precision.

    `canonical_claim` renders `price={...:.2f}` (receipt.py), so a proposal less
    than half a cent below the psi threshold fails G4 and is substituted — and
    the substitute renders to the *same cent* as the proposal. Claim and
    emission then digest alike while `override_scope` says `"value"`, which is
    the one combination `verify()` refuses: a claimed substitution with no trace
    of itself.

    The Membrane minting a receipt its own verifier rejects is the defect this
    branch was opened to close. It is reachable from the model, which sends
    `float(price)` with no cent rounding (transformer/main.py), and it is
    invisible to the grids above because they generate `round(uniform(...), 2)`
    — the precision class that structurally cannot trigger it.
    """

    # cost/(1-m) lands exactly on 111.11, so a proposal a fraction of a cent
    # under it fails the margin gate and ceils back onto the same cent.
    COST = 99.999
    THRESHOLD_CENT = 111.11

    @pytest.mark.asyncio
    async def test_a_sub_cent_proposal_still_mints_a_verifiable_receipt(self) -> None:
        from aura_hive.hive.membrane.receipt import verify

        membrane = guarded_membrane()
        intent = counter_intent(price=111.108)

        decision = await membrane.inspect_outbound(
            intent,
            Context(
                metadata=make_struct(
                    {"floor_price": "50.0", "internal_cost": str(self.COST)}
                ),
                hive=HiveContextData(request_id=""),
            ),
        )
        receipt = decision.receipt
        result = verify(receipt)

        assert result.ok, (
            f"claim={receipt.claim_hash} emission={receipt.emission_hash} "
            f"scope={receipt.override_scope!r} gate={receipt.outcome_gate} "
            f"failures={result.failures}"
        )

    @pytest.mark.asyncio
    async def test_an_override_is_recorded_only_when_the_emitted_cent_differs(
        self,
    ) -> None:
        """
        The receipt reports interventions by the difference between two digests.
        An override whose digests are identical claims a substitution the
        evidence cannot show, so at cent precision it is not an override.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=111.108),
            Context(
                metadata=make_struct(
                    {"floor_price": "50.0", "internal_cost": str(self.COST)}
                ),
                hive=HiveContextData(request_id=""),
            ),
        )

        assert decision.negotiation is not None
        assert decision.negotiation.price == self.THRESHOLD_CENT
        assert decision.receipt.claim_hash != decision.receipt.emission_hash or (
            decision.receipt.outcome != DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        )


class TestAGateThatCannotJudgeDoesNotSubstitute:
    """
    G3 fires on the *configuration*, not on the price.

    Every other gate refuses a price for being wrong, so a failing gate implies
    the proposal is strictly below a threshold the substitute is ceilinged
    above, and the two can never render to the same cent. G3 breaks that
    premise: it fires when `min_profit_margin` is unreadable, at any price at
    all — and the Membrane then substituted using the *default* margin, i.e.
    answered with the very formula the gate had just declared unevaluable.

    `ruleset.yaml` states the intent outright — "a deployment that cannot read
    its own margin setting must not answer at all rather than answer with a
    formula it cannot evaluate" — as does `_gate_settings_present`'s own
    comment. Only the Membrane disagreed.

    The receipt consequence is the one this branch exists to prevent: because
    the substitute is a fixed cent within a session, a model that echoes the
    Membrane's own last counter — ordinary convergence — proposes exactly it,
    and claim and emission digest alike under `override_scope="value"`, which
    `verify()` refuses.
    """

    class _NoMargin:
        min_profit_margin = None
        ui_trigger_price = 100000.0
        trade_risk_threshold = 0.10

    def _unjudgeable_membrane(self) -> HiveMembrane:
        registry = SkillRegistry()
        skill = GuardSkill()
        settings = self._NoMargin()
        skill.bind(settings, OutputGuard(safety_settings=settings))
        registry.register(skill.get_name(), skill)
        return HiveMembrane(registry=registry)

    @pytest.mark.asyncio
    async def test_an_unreadable_margin_refuses_instead_of_pricing(self) -> None:
        # Above the floor, so G1 and G2 both pass and G3 is the gate that
        # fires. A price below the floor trips G2 first, which is a price gate
        # and rightly substitutes.
        decision = await self._unjudgeable_membrane().inspect_outbound(
            counter_intent(price=1500.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert decision.action == ActionType.ACTION_TYPE_REJECT
        assert not decision.negotiation

    @pytest.mark.asyncio
    async def test_the_echoed_counter_no_longer_mints_a_refused_receipt(self) -> None:
        """The two-round convergence that reproduced the collision."""
        from aura_hive.hive.membrane.receipt import verify

        membrane = self._unjudgeable_membrane()

        for price in (500.0, 1111.12):
            decision = await membrane.inspect_outbound(
                counter_intent(price=price), negotiation_context()
            )
            assert verify(decision.receipt).ok, (
                f"price={price} scope={decision.receipt.override_scope!r} "
                f"failures={verify(decision.receipt).failures}"
            )


class TestAnOverrideThatChangesNothingIsNotAnOverride:
    """
    The receipt reports an intervention by the difference between two digests,
    so an OVERRIDE whose digests are identical claims a substitution the
    evidence cannot show — the exact combination `verify()` refuses.

    With G3 failing closed no live gate can reach this: G1, G2 and G4 all imply
    the proposal is strictly under a threshold the substitute is ceilinged
    above. This is the invariant that keeps it that way when the fifth gate is
    added, and it is asserted through a stubbed substitute rather than a real
    one because no real one can currently produce it.
    """

    @pytest.mark.asyncio
    async def test_a_substitute_equal_to_the_proposal_records_no_override(
        self,
    ) -> None:
        from aura_hive.hive.membrane.receipt import verify

        guard = OutputGuard(safety_settings=_Safety())
        # A gate refuses the price, and the substitute lands on the very cent
        # that was proposed.
        guard._gate_floor_violation = lambda decision, context: False  # type: ignore[method-assign]
        guard.calculate_safe_price = lambda *args, **kwargs: 1111.12  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        decision = await membrane.inspect_outbound(
            counter_intent(price=1111.12), negotiation_context()
        )

        assert decision.receipt.outcome != DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.receipt.override_scope == ""
        assert verify(decision.receipt).ok, verify(decision.receipt).failures
