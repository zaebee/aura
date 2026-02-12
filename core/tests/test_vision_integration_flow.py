import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
from aura_core import SkillRegistry
from aura_core.gen.aura.dna.v1 import (
    AgentIdentity,
    PerceptionSignal,
    Signal,
    TelegramSignal,
)
from hive.aggregator.main import HiveAggregator
from hive.proteins.perception.skill import PerceptionSkill
from hive.proteins.persistence.skill import PersistenceSkill
from hive.proteins.reasoning.skill import ReasoningSkill
from hive.transformer.main import AuraTransformer


@pytest.mark.asyncio
async def test_vision_to_listing_flow(mocker: "MockerFixture"):
    # 1. Setup Registry and Skills
    registry = SkillRegistry()

    # Mock Persistence
    persistence = mocker.Mock(spec=PersistenceSkill)
    persistence.get_name.return_value = "persistence"
    persistence.execute = AsyncMock()
    registry.register("persistence", persistence)

    # Mock Perception
    perception = mocker.Mock(spec=PerceptionSkill)
    perception.get_name.return_value = "perception"
    perception.execute = AsyncMock()
    registry.register("perception", perception)

    # Mock Guard
    guard = mocker.Mock()
    guard.get_name.return_value = "guard"
    guard.execute = AsyncMock()
    registry.register("guard", guard)

    # Mock Telemetry
    telemetry = mocker.Mock()
    telemetry.get_name.return_value = "telemetry"
    telemetry.execute = AsyncMock()
    registry.register("telemetry", telemetry)

    # 2. Simulate Perception Signal
    aggregator = HiveAggregator(registry)

    image_data = b"fake-image-bytes"
    agent_did = "tg:12345"

    signal = Signal(
        signal_id="sig-1",
        perception=PerceptionSignal(
            image_data=image_data,
            agent=AgentIdentity(did=agent_did, reputation_score=1.0)
        )
    )

    # Mock Perception result
    perception_result = {
        "id": "perceived-honda",
        "name": "2024 Honda Forza",
        "base_price": 5000.0,
        "floor_price": 4500.0,
        "meta": {"color": "Black", "confidence": "0.95"}
    }
    perception.execute.return_value = MagicMock(success=True, data=perception_result)
    guard.execute.return_value = MagicMock(success=True)
    telemetry.execute.return_value = MagicMock(success=True, data={"cpu_usage_percent": 10.0, "memory_usage_mb": 100.0, "status": "ok", "timestamp": "now"})

    # Perceive
    context = await aggregator.perceive(bytes(signal))

    # Verify Persistence was called to set cache
    persistence.execute.assert_any_call(
        "set_cache", {
            "key": f"ephemeral:asset:{agent_did}",
            "value": perception_result,
            "expire": 3600
        }
    )

    assert context.item_data == perception_result
    assert context.metadata["source"] == "vision"

    # 3. Simulate Callback Signal (List Now)
    callback_signal = Signal(
        signal_id="sig-2",
        telegram=TelegramSignal(
            user_id=12345,
            callback_data="list_now:perceived-honda:5400.0"
        )
    )

    # Mock Persistence to return cached asset
    persistence.execute.reset_mock()
    persistence.execute.side_effect = [
        MagicMock(success=True, data=perception_result), # For get_cache
        MagicMock(success=True, data=None), # For read_item (fallback)
    ]

    # Re-perceive with callback
    context_cb = await aggregator.perceive(bytes(callback_signal))

    assert context_cb.item_data == perception_result
    assert context_cb.offer.bid_amount == 5400.0
    assert context_cb.metadata["source"] == "telegram"

    # 4. Transformer reasoning
    transformer = AuraTransformer(registry)
    reasoning = mocker.Mock(spec=ReasoningSkill)
    reasoning.get_name.return_value = "reasoning"
    reasoning.execute = AsyncMock()
    registry.register("reasoning", reasoning)

    # Mock reasoning to accept
    reasoning.execute.return_value = MagicMock(success=True, data={
        "action": "accept",
        "price": 5400.0,
        "message": "Listed!",
        "thought": "User accepted appraisal.",
        "metadata": {}
    })

    decision = await transformer.think(context_cb)

    assert decision.action.name == "ACTION_TYPE_ACCEPT"
    assert decision.price == 5400.0
    # Verify vision_result was propagated in metadata for the event
    assert "vision_result" in decision.metadata
    assert json.loads(decision.metadata["vision_result"]) == perception_result
