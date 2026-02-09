import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from aura_core import HiveContext, NegotiationOffer, SystemVitals, IntentAction
from hive.transformer.main import AuraTransformer
from aura_core.gen.aura.dna.v1 import ActionType

@pytest.mark.asyncio
async def test_semantic_cache_hit():
    registry = MagicMock()
    settings = MagicMock()
    transformer = AuraTransformer(registry, settings)

    context = HiveContext(
        item_id="item_123",
        offer=NegotiationOffer(bid_amount=100.0, reputation=1.0),
        item_data={"base_price": 120.0, "floor_price": 90.0},
        system_health=SystemVitals(status="healthy", cpu_usage_percent=10.0)
    )

    # Mock cache hit
    mock_obs = MagicMock()
    mock_obs.success = True
    mock_obs.data = {
        "action": "accept",
        "price": 100.0,
        "message": "Cached accept",
        "thought": "Cached thought",
        "metadata": {}
    }
    registry.execute = AsyncMock(return_value=mock_obs)

    result = await transformer.think(context)

    assert result.message == "Cached accept"
    assert result.metadata.get("cached") is True
    # Verify first call was get_cache
    assert registry.execute.call_args_list[0][0][0] == "persistence"
    assert registry.execute.call_args_list[0][0][1] == "get_cache"

@pytest.mark.asyncio
async def test_rate_limit_fallback():
    registry = MagicMock()
    settings = MagicMock()
    # Mock settings.safety.ui_trigger_price
    settings.safety = MagicMock()
    settings.safety.ui_trigger_price = 1000.0
    settings.llm = MagicMock()
    settings.llm.model = "gpt-4"

    transformer = AuraTransformer(registry, settings)

    context = HiveContext(
        item_id="item_123",
        offer=NegotiationOffer(bid_amount=100.0, reputation=1.0),
        item_data={"base_price": 120.0, "floor_price": 90.0},
        system_health=SystemVitals(status="healthy", cpu_usage_percent=10.0)
    )

    # Mock cache miss and then rate limit error
    cache_miss_obs = MagicMock()
    cache_miss_obs.success = False

    rate_limit_obs = MagicMock()
    rate_limit_obs.success = False
    rate_limit_obs.error = "RateLimitError: model overloaded"

    registry.execute = AsyncMock(side_effect=[cache_miss_obs, rate_limit_obs])

    result = await transformer.think(context)

    # Should fallback to RuleBasedStrategy
    # Since bid (100) > floor (90), it should accept
    assert result.action == ActionType.ACTION_TYPE_ACCEPT
    # RuleBasedStrategy thought contains "at or above floor price"
    assert "at or above floor price" in result.thought
