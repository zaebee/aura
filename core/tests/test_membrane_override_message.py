"""
What the counterparty reads when the guard intervened.

Withholding the receipt's `outcome` field does nothing while the message says
"I've reached my final limit": the override announced itself in plain English,
and the substitute price is a function of the hidden floor. The message is one
half of that; the jitter in the price is the other.
"""

import pytest

from .test_membrane_postcondition import (
    counter_intent,
    guarded_membrane,
    negotiation_context,
)


class TestTheMessageDoesNotAnnounceTheGuard:
    @pytest.mark.asyncio
    async def test_no_finality_language(self) -> None:
        membrane = guarded_membrane()
        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )
        message = result.negotiation.message.lower()
        for tell in ("final limit", "best offer", "cannot disclose", "membrane"):
            assert tell not in message

    @pytest.mark.asyncio
    async def test_a_price_is_still_stated(self) -> None:
        """
        Neutral is not silent. The counterparty needs the number; what they must
        not get is a label saying which rule produced it.
        """
        membrane = guarded_membrane()
        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )
        assert f"{result.negotiation.price:.2f}" in result.negotiation.message


class TestJitterIsSessionStable:
    @pytest.mark.asyncio
    async def test_repeated_rounds_return_the_same_price(self) -> None:
        """
        Redrawn per decision, a counterparty averages the noise away over rounds
        and recovers the floor anyway.
        """
        prices = set()
        for _ in range(5):
            membrane = guarded_membrane()
            result = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context(request_id="sess-abc")
            )
            prices.add(result.negotiation.price)
        assert len(prices) == 1

    @pytest.mark.asyncio
    async def test_a_different_session_returns_a_different_price(self) -> None:
        prices = set()
        for n in range(20):
            membrane = guarded_membrane()
            result = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context(request_id=f"r-{n}")
            )
            prices.add(result.negotiation.price)
        assert len(prices) > 1
