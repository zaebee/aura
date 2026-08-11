"""
The Membrane does not edit the Intent it was handed.

Filed as #257 when the outbound path mixed two styles: DLP rewrote the caller's
Intent in place while the refusals and the override returned a different one.
The recommendation there was to mutate everywhere, matching `inspect_inbound`.

That recommendation was wrong, and the receipt work is what made it wrong.
`_finish` computes `claim_hash` from the Intent the Transformer proposed and
`emission_hash` from the one being sent; mutating the first to produce the
second leaves one object, so both hashes are taken after the change and the
receipt reports no intervention. The evidence of what the Membrane did lives in
the difference between two objects, so there have to be two.
"""

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    Intent,
    IntentStep,
    NegotiationIntent,
    RWAComplianceScore,
    RWAVaultIntent,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


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


def context(floor: float = 1000.0) -> Context:
    return Context(metadata=make_struct({"floor_price": str(floor)}))


def rich_intent(price: float, message: str = "an offer") -> Intent:
    """Carries the fields a hand-written replacement is most likely to forget."""
    return Intent(
        identifier="decision-1",
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="what the model thought",
        steps=[IntentStep(skill="reasoning", intent="price")],
        metadata=make_struct({"trace_note": "keep me"}),
        negotiation=NegotiationIntent(price=price, message=message),
    )


class TestTheCallersIntentSurvivesUntouched:
    @pytest.mark.asyncio
    async def test_a_sanitised_message_is_not_written_back_to_the_caller(self) -> None:
        """
        DLP rewrote `neg_intent.message` and appended to `reasoning` on the
        object it was given, and then — on the floor path — returned a different
        one. A caller keeping its reference held an Intent that had been edited
        and was not the one sent.
        """
        original = rich_intent(price=2000.0, message="our floor_price is 1000")

        await guarded_membrane().inspect_outbound(original, context())

        assert original.negotiation.message == "our floor_price is 1000"
        assert original.reasoning == "what the model thought"

    @pytest.mark.asyncio
    async def test_an_override_leaves_the_proposal_alone(self) -> None:
        original = rich_intent(price=500.0)

        await guarded_membrane().inspect_outbound(original, context())

        assert original.negotiation.price == 500.0
        assert original.action == ActionType.ACTION_TYPE_COUNTER

    @pytest.mark.asyncio
    async def test_a_refusal_leaves_the_proposal_alone(self) -> None:
        original = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(
                wallet_address="0xdead",
                compliance=RWAComplianceScore(kyc_passed=False),
            ),
        )

        await guarded_membrane().inspect_outbound(original, context())

        assert original.action == ActionType.ACTION_TYPE_APPROVE


class TestAReplacementKeepsWhatDescribesTheDecisionPoint:
    @pytest.mark.asyncio
    async def test_an_override_keeps_the_steps(self) -> None:
        """
        `steps` records how the decision was reached upstream. A replacement
        built field by field drops it silently — the constructor is happy to
        default it, and nothing warns.
        """
        sent = await guarded_membrane().inspect_outbound(
            rich_intent(price=500.0), context()
        )

        assert [s.skill for s in sent.steps] == ["reasoning"]

    @pytest.mark.asyncio
    async def test_an_override_keeps_metadata_it_did_not_set_itself(self) -> None:
        sent = await guarded_membrane().inspect_outbound(
            rich_intent(price=500.0), context()
        )

        assert sent.metadata.to_dict()["trace_note"] == "keep me"

    @pytest.mark.asyncio
    async def test_the_overrides_own_metadata_still_wins(self) -> None:
        """
        `_override_with_safe_offer` records what it replaced. Carrying the
        original's metadata must not bury that.
        """
        sent = await guarded_membrane().inspect_outbound(
            rich_intent(price=500.0), context()
        )
        meta = sent.metadata.to_dict()

        assert meta["override_reason"] == "FLOOR_PRICE_VIOLATION"
        assert meta["original_price"] == "500.0"


class TestTheInterventionStaysVisible:
    """
    Why replacement rather than mutation. The receipt reports what the Membrane
    did by comparing two digests; one object cannot produce two.
    """

    @pytest.mark.asyncio
    async def test_a_refusal_shows_the_action_it_changed(self) -> None:
        sent = await guarded_membrane().inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_APPROVE,
                rwa_vault=RWAVaultIntent(
                    wallet_address="0xdead",
                    compliance=RWAComplianceScore(kyc_passed=False),
                ),
            ),
            context(),
        )

        assert sent.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert sent.receipt.claim_hash != sent.receipt.emission_hash

    @pytest.mark.asyncio
    async def test_a_sanitised_message_alone_still_hashes_alike(self) -> None:
        """
        Unchanged by this: prose is outside the claim, so a DLP-only override
        shows equal digests and is visible through `outcome`. Building a
        replacement rather than mutating does not alter that.
        """
        sent = await guarded_membrane().inspect_outbound(
            rich_intent(price=2000.0, message="our floor_price is 1000"), context()
        )

        assert sent.receipt.outcome_gate == "DLP_BLOCK"
        assert sent.receipt.claim_hash == sent.receipt.emission_hash
        assert sent.negotiation.message != "our floor_price is 1000"
