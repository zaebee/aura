"""
The derivation travels with the Intent that was actually sent.

`outcome_gate` says which rule refused a decision. It does not say which rules
were consulted first, so on its own it cannot be replayed: two deployments could
report the same failing gate having evaluated different sets on the way there.
The gate sequence closes that, and `derivation_hash` lets a reader confirm the
sequence has not been edited before paying to replay it
(docs/DECISION_RECEIPT.md §3.4).

Nothing here is worth having if the record leaks a number, so that is asserted
against the Intent itself rather than only against the engine that built it.
"""

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    Intent,
    NegotiationIntent,
    Observation,
    RWAComplianceScore,
    RWAVaultIntent,
    TradeIntent,
    ValidationScore,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard

FLOOR = 1000.0


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 1000.0
    trade_risk_threshold = 0.10


def guarded_membrane() -> HiveMembrane:
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    return HiveMembrane(registry=registry)


def negotiation_context(floor_price: float = FLOOR) -> Context:
    return Context(
        metadata=make_struct(
            {"floor_price": str(floor_price), "internal_cost": "777.0"}
        )
    )


def counter_intent(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


class TestTheDerivationReachesTheIntent:
    @pytest.mark.asyncio
    async def test_an_emitted_decision_carries_the_gates_it_passed(self) -> None:
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.derivation.gate_sequence.startswith("G1_PRICE_POSITIVE:pass:")
        assert "G4_MARGIN_VIOLATION:pass:" in decision.derivation.gate_sequence
        assert len(decision.derivation.derivation_hash) == 64

    @pytest.mark.asyncio
    async def test_an_overridden_decision_carries_the_gate_that_stopped_it(
        self,
    ) -> None:
        """
        The override builds a fresh Intent, so the record has to be carried over
        deliberately — the same trap `identifier` and `trace` fell into.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.derivation.gate_sequence == (
            "G1_PRICE_POSITIVE:pass:price\x1fG2_FLOOR_VIOLATION:fail:price,floor_price"
        )
        assert len(decision.derivation.derivation_hash) == 64

    @pytest.mark.asyncio
    async def test_the_hash_matches_the_sequence_that_travelled(self) -> None:
        """
        The pair is redundant on purpose: a reader confirms the two agree with
        one hash compare and only then pays to replay the steps.
        """
        import hashlib

        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert (
            decision.derivation.derivation_hash
            == hashlib.sha256(
                decision.derivation.gate_sequence.encode("utf-8")
            ).hexdigest()
        )


class TestReplay:
    """
    The claim the digest makes is that someone else can re-derive it. A digest
    reproducible only inside one process is worth nothing to the party it is
    handed to.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_the_same_decision_derives_byte_identically_twice(
        self, price: float
    ) -> None:
        """
        Fresh Membrane, fresh registry, fresh guard on each run — anything that
        survived between them would be state the verifier does not have.
        """
        first = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )
        second = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )

        assert first.derivation.gate_sequence == second.derivation.gate_sequence
        assert first.derivation.derivation_hash == second.derivation.derivation_hash

    @pytest.mark.asyncio
    async def test_a_different_floor_changing_the_verdict_changes_the_digest(
        self,
    ) -> None:
        """
        The digest tracks the steps, so it moves when the steps do — here
        because a higher floor makes G2 fail where it had passed.
        """
        passing = await guarded_membrane().inspect_outbound(
            counter_intent(price=1500.0), negotiation_context(floor_price=1000.0)
        )
        failing = await guarded_membrane().inspect_outbound(
            counter_intent(price=1500.0), negotiation_context(floor_price=9000.0)
        )

        assert passing.derivation.derivation_hash != failing.derivation.derivation_hash

    @pytest.mark.asyncio
    async def test_a_different_floor_leaving_the_verdict_alone_does_not(self) -> None:
        """
        The other half of the same property, and the one that keeps the digest
        from being a value oracle: two different floors that both pass every
        gate derive identically, so the digest cannot be probed for the floor.
        """
        low = await guarded_membrane().inspect_outbound(
            counter_intent(price=5000.0), negotiation_context(floor_price=1000.0)
        )
        high = await guarded_membrane().inspect_outbound(
            counter_intent(price=5000.0), negotiation_context(floor_price=2000.0)
        )

        assert low.derivation.derivation_hash == high.derivation.derivation_hash


class TestTheIntentNeverCarriesAValue:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_no_hidden_number_appears_in_the_sequence(self, price: float) -> None:
        """
        The floor and the internal cost are the two things the Membrane spends
        its outbound path keeping off the wire. A field meant to be published
        must not put them back.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=price), negotiation_context(floor_price=FLOOR)
        )

        sequence = decision.derivation.gate_sequence
        for secret in ("1000", "777", str(price), str(int(price))):
            assert secret not in sequence


class TestAGuardThatReportsNothingUsable:
    """
    The Membrane reads the record out of whatever the guard skill reported, and
    a skill is free to report an Observation it did not fill in.

    Neither case below is reachable from `GuardSkill` today, which always
    returns both keys as strings. They are guarded because this PR moved
    `metadata.to_dict()` onto the passing path, where it had never run before —
    the failure path was the only caller until now — and because attaching a
    derivation built from junk is the exact thing the empty-record rule exists
    to prevent.
    """

    class _SilentGuard:
        """A guard protein that answers without filling in its metadata."""

        def __init__(self, observation: Observation) -> None:
            self._observation = observation

        def get_name(self) -> str:
            return "guard"

        async def execute(self, intent: str, params: dict) -> Observation:
            return self._observation

    def membrane_reporting(self, observation: Observation) -> HiveMembrane:
        registry = SkillRegistry()
        registry.register("guard", self._SilentGuard(observation))
        return HiveMembrane(registry=registry)

    @pytest.mark.asyncio
    async def test_an_observation_without_metadata_does_not_take_the_guard_down(
        self,
    ) -> None:
        """
        A crash here would lose the negotiation, and it would do so inside the
        one component whose job is to never let a bad decision out.
        """
        membrane = self.membrane_reporting(Observation(success=True, metadata=None))

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_null_valued_record_is_not_attached_as_the_word_none(self) -> None:
        """
        `str(None)` is "None", which is truthy — so the naive read would attach a
        DecisionDerivation whose sequence is the literal text None and whose
        hash claims a derivation that never ran.
        """
        membrane = self.membrane_reporting(
            Observation(
                success=True,
                metadata=make_struct({"gate_sequence": None, "derivation_hash": None}),
            )
        )

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.derivation.gate_sequence == ""
        assert decision.derivation.derivation_hash == ""


class TestNoDeclaredGateRan:
    """
    These paths refuse or emit without consulting the rule set, so they have no
    derivation to show. Attaching an empty-string hash would be a claim that
    something was derived; leaving the field unset says plainly that nothing was.

    The Membrane's own checks — KYC, trade risk, DLP — are not declared in any
    rule set yet, so they cannot be recorded as gates without inventing ids
    nothing versions (docs/DECISION_RECEIPT.md §3.3).
    """

    @pytest.mark.asyncio
    async def test_a_kyc_refusal_shows_no_derivation(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(
                wallet_address="0xdead",
                compliance=RWAComplianceScore(kyc_passed=False),
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.derivation.gate_sequence == ""
        assert decision.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_high_risk_trade_refusal_shows_no_derivation(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                validation_score=ValidationScore(
                    risk_score=0.9, risk_category="EXTREME"
                )
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_model_reject_shows_no_derivation(self) -> None:
        """The guard is never consulted: only accept and counter put a price out."""
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_REJECT,
                negotiation=NegotiationIntent(price=0.0, message="no thanks"),
            ),
            negotiation_context(),
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_an_unwired_membrane_shows_no_derivation(self) -> None:
        """
        No registry means no guard ran. Claiming a derivation here would be the
        worst version of the lie: a receipt asserting gates on a deployment that
        has none wired.
        """
        membrane = HiveMembrane(registry=None)

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.derivation.derivation_hash == ""
