from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core import SkillRegistry
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    HiveContextData,
    NegotiationOffer,
    Observation,
)

from hive.transformer import AuraTransformer

@pytest.mark.asyncio
async def test_aura_transformer_nested_action_fix():
    # Setup registry and mock reasoning skill
    registry = SkillRegistry()
    reasoning_skill = MagicMock()
    reasoning_skill.execute = AsyncMock()
    registry.register("reasoning", reasoning_skill)

    # Mock reasoning result with NESTED action (The way DSPy AuraNegotiator returns it)
    nested_result = {
        "thought": "I should accept this bid.",
        "action": {
            "action": "accept",
            "price": 100.0,
            "message": "Offer accepted."
        }
    }

    mock_observation = Observation(
        success=True,
        metadata=protobuf.Struct().from_dict(nested_result)
    )
    reasoning_skill.execute.return_value = mock_observation

    # Initialize transformer
    transformer = AuraTransformer(registry=registry)

    # Create context
    context = Context(
        hive=HiveContextData(
            offer=NegotiationOffer(bid_amount=100.0)
        )
    )

    # Execute think
    intent = await transformer.think(context)

    # Assertions
    assert intent.action == ActionType.ACTION_TYPE_ACCEPT
    assert intent.negotiation.price == 100.0
    assert intent.negotiation.message == "Offer accepted."
    assert "<think>" in intent.reasoning
    assert "I should accept this bid." in intent.reasoning

@pytest.mark.asyncio
async def test_aura_transformer_flat_action_fallback():
    # Setup registry and mock reasoning skill
    registry = SkillRegistry()
    reasoning_skill = MagicMock()
    reasoning_skill.execute = AsyncMock()
    registry.register("reasoning", reasoning_skill)

    # Mock reasoning result with FLAT action (Legacy or alternate format)
    flat_result = {
        "thought": "I should counter this bid.",
        "action": "counter",
        "price": 150.0,
        "message": "Too low."
    }

    mock_observation = Observation(
        success=True,
        metadata=protobuf.Struct().from_dict(flat_result)
    )
    reasoning_skill.execute.return_value = mock_observation

    # Initialize transformer
    transformer = AuraTransformer(registry=registry)

    # Create context
    context = Context(
        hive=HiveContextData(
            offer=NegotiationOffer(bid_amount=100.0)
        )
    )

    # Execute think
    intent = await transformer.think(context)

    # Assertions
    assert intent.action == ActionType.ACTION_TYPE_COUNTER
    assert intent.negotiation.price == 150.0
    assert intent.negotiation.message == "Too low."
