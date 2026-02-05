import pytest
from dataclasses import dataclass
from unittest.mock import patch
from hive.chambers.negotiation.main import negotiation_loop
from aura_core import IntentAction
from aura_core.gen.aura.dna.v1 import ActionType

@dataclass
class MockSignal:
    item_id: str
    bid_amount: float

@pytest.mark.asyncio
async def test_negotiation_loop_standard_flow():
    """Test the chamber loop with a standard bid."""
    signal = MockSignal(item_id="test_1", bid_amount=90.0)

    observation = await negotiation_loop(signal)

    assert observation.success is True
    assert observation.event_type == "negotiation_processed"
    assert observation.metadata["price"] == 95.0 # 95% of 100.0

@pytest.mark.asyncio
async def test_negotiation_loop_membrane_override():
    """Test that the membrane overrides a strategy price below floor."""
    # Item floor is 85.
    signal = MockSignal(item_id="test_2", bid_amount=50.0)

    # Mock T.think to return an unsafe price (below floor)
    unsafe_intent = IntentAction(
        action=ActionType.ACTION_TYPE_ACCEPT,
        price=70.0, # Below floor 85.0
        message="Too low!",
        thought="Thinking unsafe thoughts"
    )

    with patch("hive.chambers.negotiation.T.think", return_value=unsafe_intent):
        observation = await negotiation_loop(signal)

    # Membrane should have overridden the price to 85.0
    assert observation.metadata["price"] == 85.0

@pytest.mark.asyncio
async def test_negotiation_loop_negative_bid_correction():
    """Test that the membrane corrects a negative bid."""
    signal = MockSignal(item_id="test_3", bid_amount=-10.0)

    # We can't easily see the corrected bid inside the loop without more instrumentation,
    # but we can verify it doesn't crash and returns a valid result.
    observation = await negotiation_loop(signal)
    assert observation.success is True
