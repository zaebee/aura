"""
The dispute token survives every hop between the Membrane and the client.

Each message in that chain is re-assembled field by field rather than passed
along, so anything that has to reach the client must be copied deliberately at
each one. The receipt used to be that thing and used to die at the first hop —
`NegotiationObservation` simply had no field for it.

The receipt no longer travels here at all. It is addressed to an auditor
(DECISION_RECEIPT.md §1.1) and reaches them through the Membrane's structured
log; handing it to the party we negotiate against reconstructs most of the
hidden floor. What travels is a random per-decision handle they can cite, which
the auditor resolves — so the copy-at-every-hop hazard is unchanged and these
tests still guard it.
"""

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    NegotiationIntent,
    NegotiationObservation,
)
from aura_hive.hive.connector.main import HiveConnector

TOKEN = "7c1b4a2e-0000-4000-8000-abcdefabcdef"


def counter_intent_with_token() -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        negotiation=NegotiationIntent(price=105.0, message="my best offer"),
        dispute_token=TOKEN,
    )


def connector() -> HiveConnector:
    return HiveConnector(SkillRegistry())


def context() -> Context:
    return Context(metadata=make_struct({"floor_price": "100.0"}))


class TestTheTokenReachesTheObservation:
    @pytest.mark.asyncio
    async def test_a_countered_offer_carries_its_token(self) -> None:
        observation = await connector().act(counter_intent_with_token(), context())

        assert observation.negotiation.dispute_token == TOKEN

    @pytest.mark.asyncio
    async def test_a_rejected_offer_carries_it_too(self) -> None:
        """
        Copied before the result branches, so no branch can be the one that
        forgets. A rejection is exactly as disputable as a counter.
        """
        rejection = Intent(
            action=ActionType.ACTION_TYPE_REJECT,
            negotiation=NegotiationIntent(price=0.0),
            dispute_token=TOKEN,
        )

        observation = await connector().act(rejection, context())

        assert observation.negotiation.dispute_token == TOKEN

    @pytest.mark.asyncio
    async def test_an_intent_without_a_token_does_not_invent_one(self) -> None:
        untouched = Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            negotiation=NegotiationIntent(price=105.0),
        )

        observation = await connector().act(untouched, context())

        assert observation.negotiation.dispute_token == ""


class TestTheReceiptDoesNotTravelThisWay:
    def test_the_observation_has_no_receipt_field_left(self) -> None:
        """
        Structural rather than a matter of the Connector being careful: field 8
        is reserved, so there is no hop left to leak through.
        """
        assert not hasattr(NegotiationObservation(), "receipt")
