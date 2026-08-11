"""
The receipt survives every hop between the Membrane and the client.

Each message in that chain is re-assembled field by field rather than passed
along, so the receipt has to be copied deliberately at each one. It used to die
at the first — `NegotiationObservation` simply had no field for it — and a
receipt that stops inside the process is a receipt nobody outside can read,
which is the only audience it has.
"""

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    DecisionReceipt,
    Intent,
    NegotiationIntent,
    ReceiptSignature,
)
from aura_hive.hive.connector.main import HiveConnector


def counter_intent_with_receipt() -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        negotiation=NegotiationIntent(price=105.0, message="my best offer"),
        receipt=DecisionReceipt(
            version="AURA-RECEIPT-V2",
            claim_hash="a" * 64,
            emission_hash="b" * 64,
            ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
            canonical_prefix="c0ffee1234abcd56",
            signature=ReceiptSignature(signer="0xabc", signature="0xdef"),
        ),
    )


class TestTheConnectorCarriesItOut:
    @pytest.mark.asyncio
    async def test_a_countered_offer_carries_its_receipt(self) -> None:
        observation = await HiveConnector(SkillRegistry()).act(
            counter_intent_with_receipt(), Context(metadata=make_struct({}))
        )

        assert observation.negotiation.receipt.canonical_prefix == "c0ffee1234abcd56"
        assert observation.negotiation.receipt.outcome_gate == "FLOOR_PRICE_VIOLATION"

    @pytest.mark.asyncio
    async def test_the_signature_survives_the_hop(self) -> None:
        """
        A receipt whose signature was dropped en route verifies as unsigned,
        which is worse than being absent: it looks like a deployment with no key
        rather than a transport that lost the attestation.
        """
        observation = await HiveConnector(SkillRegistry()).act(
            counter_intent_with_receipt(), Context(metadata=make_struct({}))
        )

        assert observation.negotiation.receipt.signature.signer == "0xabc"

    @pytest.mark.asyncio
    async def test_a_rejected_offer_carries_it_too(self) -> None:
        """Refusals are the decisions a counterparty most wants to check."""
        intent = counter_intent_with_receipt()
        intent.action = ActionType.ACTION_TYPE_REJECT

        observation = await HiveConnector(SkillRegistry()).act(
            intent, Context(metadata=make_struct({}))
        )

        assert observation.negotiation.receipt.canonical_prefix == "c0ffee1234abcd56"

    @pytest.mark.asyncio
    async def test_an_intent_without_a_receipt_does_not_invent_one(self) -> None:
        intent = Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            negotiation=NegotiationIntent(price=105.0),
        )

        observation = await HiveConnector(SkillRegistry()).act(
            intent, Context(metadata=make_struct({}))
        )

        assert observation.negotiation.receipt.canonical_prefix == ""
