"""
The Membrane says what it did to the decision, in a typed field.

Until this existed, the only trace of an intervention was a Prometheus counter
(aggregate, not per-decision) and a sentence appended to free-text `reasoning`.
Neither travels with the Intent to whoever consumes it: a counterparty reading
an offer could not tell whether the price came from the model or from the guard
that overruled it, and an auditor replaying one negotiation had to parse prose.

`outcome` makes the distinction a fact on the wire. `outcome_gate` names the
invariant that fired, using the guard's own error code rather than a generic
bucket, so the field answers "which rule" and not merely "some rule".
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
    RWAComplianceScore,
    RWAVaultIntent,
    TraceContext,
    TradeIntent,
    ValidationScore,
)
from aura_hive.hive.membrane.main import HiveMembrane
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

    `inspect_outbound` returns early when `self.registry` is None, so an unwired
    Membrane passes every price through untouched and would mark it EMIT.
    """
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    return HiveMembrane(registry=registry)


def negotiation_context(floor_price: float = 1000.0) -> Context:
    return Context(metadata=make_struct({"floor_price": str(floor_price)}))


def counter_intent(price: float, message: str = "Here is my offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message=message),
    )


class TestEmit:
    @pytest.mark.asyncio
    async def test_an_untouched_decision_is_marked_emit(self) -> None:
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context(floor_price=1000.0)
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.outcome_gate == ""

    @pytest.mark.asyncio
    async def test_a_decision_the_guard_never_saw_is_still_marked_emit(self) -> None:
        """
        An unwired Membrane makes no claim about the price, but it must still
        claim that it did not alter one. UNSPECIFIED would be indistinguishable
        from a field nobody set.
        """
        membrane = HiveMembrane(registry=None)

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context(floor_price=1000.0)
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT


class TestOverride:
    @pytest.mark.asyncio
    async def test_a_price_below_floor_is_marked_override(self) -> None:
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context(floor_price=1000.0)
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.outcome_gate == "FLOOR_PRICE_VIOLATION"

    @pytest.mark.asyncio
    async def test_the_substituted_price_travels_with_the_override_mark(self) -> None:
        """The mark is worthless if it does not sit on the Intent actually sent."""
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context(floor_price=1000.0)
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.negotiation.price != 500.0

    @pytest.mark.asyncio
    async def test_a_sanitised_message_is_marked_override(self) -> None:
        """
        DLP rewrites the message in place rather than going through the safe-offer
        path, but the emitted Intent is still not the one the model produced.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0, message="our floor_price is 1000"),
            negotiation_context(floor_price=1000.0),
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.outcome_gate == "DLP_BLOCK"

    @pytest.mark.asyncio
    async def test_the_first_gate_to_fire_is_the_one_recorded(self) -> None:
        """
        A decision that trips DLP and then the floor check records DLP_BLOCK,
        the earlier gate.

        Recording every gate that fired would hand an adversary an oracle over
        the policy configuration: probe with crafted offers, read back the full
        set, and the shape of the hidden floor falls out. One binding reason.

        Note this constrains only what is *recorded*. Both gates still execute —
        short-circuiting the floor check to save a field would trade a guarantee
        for a label.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0, message="our floor_price is 1000"),
            negotiation_context(floor_price=1000.0),
        )

        assert decision.outcome_gate == "DLP_BLOCK"
        # The later gate still ran: the price was replaced, not merely flagged.
        assert decision.negotiation.price != 500.0


class TestRefuse:
    @pytest.mark.asyncio
    async def test_a_failed_kyc_is_marked_refuse(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(
                wallet_address="0xdead",
                compliance=RWAComplianceScore(
                    kyc_passed=False, violation_code="SANCTIONS_HIT"
                ),
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.outcome_gate == "KYC_FAILURE"
        assert decision.action == ActionType.ACTION_TYPE_REJECT

    @pytest.mark.asyncio
    async def test_a_high_risk_trade_is_marked_refuse(self) -> None:
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

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.outcome_gate == "HIGH_RISK_TRADE"
        assert decision.action == ActionType.ACTION_TYPE_REJECT

    @pytest.mark.asyncio
    async def test_a_clean_trade_is_marked_emit(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                validation_score=ValidationScore(risk_score=0.01, risk_category="LOW")
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.outcome_gate == ""


class TestFailureRecovery:
    @pytest.mark.asyncio
    async def test_an_llm_error_is_marked_override(self) -> None:
        """
        The Transformer failing is not the counterparty being refused: the
        Membrane substitutes a safe offer and the negotiation continues. That is
        an override, and calling it a refusal would misreport what was sent.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(action=ActionType.ACTION_TYPE_ERROR, reasoning="LLM blew up"),
            negotiation_context(floor_price=1000.0),
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.outcome_gate == "FAILURE_RECOVERY"


class TestReplacementPreservesIdentity:
    """
    Three outbound paths do not edit the Intent they were given, they return a
    different one: the two refusals and the safe-offer override. A replacement
    describes the same decision point as the Intent it stands in for, so the
    fields that name that point have to survive the swap.

    Nothing reads `Intent.trace` today — the trace that reaches the Observation
    comes from `Context.trace` by way of the Connector, and the Transformer
    never populates the Intent's copy. So this is not repairing a broken trace;
    it is keeping a replacement honest about which decision it replaced, before
    some later consumer starts believing the field.
    """

    TRACE = TraceContext(trace_id="0af7651916cd43dd", span_id="b7ad6b7169203331")

    @pytest.mark.asyncio
    async def test_an_override_keeps_the_original_trace_and_identifier(self) -> None:
        membrane = guarded_membrane()
        original = counter_intent(price=500.0)
        original.identifier = "decision-42"
        original.trace = self.TRACE

        decision = await membrane.inspect_outbound(
            original, negotiation_context(floor_price=1000.0)
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.identifier == "decision-42"
        assert decision.trace.trace_id == "0af7651916cd43dd"

    @pytest.mark.asyncio
    async def test_a_kyc_refusal_keeps_the_original_trace_and_identifier(self) -> None:
        membrane = guarded_membrane()
        original = Intent(
            identifier="decision-43",
            action=ActionType.ACTION_TYPE_APPROVE,
            trace=self.TRACE,
            rwa_vault=RWAVaultIntent(
                wallet_address="0xdead",
                compliance=RWAComplianceScore(kyc_passed=False),
            ),
        )

        decision = await membrane.inspect_outbound(original, negotiation_context())

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.identifier == "decision-43"
        assert decision.trace.trace_id == "0af7651916cd43dd"

    @pytest.mark.asyncio
    async def test_a_trade_refusal_keeps_the_original_trace_and_identifier(
        self,
    ) -> None:
        membrane = guarded_membrane()
        original = Intent(
            identifier="decision-44",
            action=ActionType.ACTION_TYPE_APPROVE,
            trace=self.TRACE,
            trade=TradeIntent(
                validation_score=ValidationScore(
                    risk_score=0.9, risk_category="EXTREME"
                )
            ),
        )

        decision = await membrane.inspect_outbound(original, negotiation_context())

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.identifier == "decision-44"
        assert decision.trace.trace_id == "0af7651916cd43dd"


class TestPassThrough:
    @pytest.mark.asyncio
    async def test_a_reject_from_the_model_is_not_claimed_as_a_refusal(self) -> None:
        """
        `outcome` describes what the *Membrane* did, not what the model decided.
        A model that rejects on its own passed every gate, so the Membrane emitted
        it unchanged; marking it REFUSE would attribute the guard's authority to a
        decision the guard never made.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_REJECT,
                reasoning="not worth it",
                negotiation=NegotiationIntent(price=0.0, message="no thanks"),
            ),
            negotiation_context(floor_price=1000.0),
        )

        assert decision.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.outcome_gate == ""
