import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
from aura_core import SkillRegistry
from aura_core.gen.aura.core.v1 import (
    AgentIdentity,
    PerceptionSignal,
    Signal,
    TelegramSignal,
    Observation,
    NegotiationIntent,
)
from aura_core.gen.aura.assets import v1 as asset_pb2
from hive.aggregator.main import HiveAggregator
from hive.proteins.perception.skill import PerceptionSkill
from hive.proteins.persistence.skill import PersistenceSkill
from hive.proteins.reasoning.skill import ReasoningSkill
from hive.transformer.main import AuraTransformer
from aura_core.gen.aura.core.v1.google import protobuf


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
        identifier="sig-1",
        perception=PerceptionSignal(
            image_data=image_data,
            agent=AgentIdentity(did=agent_did, reputation_score=1.0)
        )
    )

    # Mock Perception result
    asset = asset_pb2.Asset(
        identifier="perceived-honda",
        vehicle=asset_pb2.VehicleAttributes(
            brand="Honda",
            model="Forza",
            year=2024
        ),
        rental_terms=asset_pb2.RentalTerms(
            price_tiers=[asset_pb2.PriceTier(price_per_day=5000.0)]
        )
    )

    any_payload = protobuf.Any()
    any_payload.value = bytes(asset)

    perception.execute.return_value = Observation(success=True, payload=any_payload)
    guard.execute.return_value = Observation(success=True)
    telemetry.execute.return_value = Observation(success=True)

    # Perceive
    context = await aggregator.perceive(signal)

    # Verify Persistence was called to set cache
    persistence.execute.assert_any_call(
        "set_cache", {
            "key": f"ephemeral:asset:{agent_did}",
            "value": {
                "make": "Honda",
                "model": "Forza",
                "year": 2024,
                "confidence_score": 0.0
            },
            "expire": 3600
        }
    )

    assert context.hive.item_identifier == "perceived-honda"
    assert context.metadata["source"] == "vision"

    # 3. Simulate Callback Signal (List Now)
    callback_signal = Signal(
        identifier="sig-2",
        telegram=TelegramSignal(
            user_id=12345,
            callback_data="list_now:perceived-honda:5400.0"
        )
    )

    # Mock Persistence to return cached asset
    persistence.execute.reset_mock()
    persistence.execute.side_effect = [
        Observation(success=True, payload=any_payload), # For get_cache
        Observation(success=True, payload=None), # For read_item (fallback)
    ]

    # Re-perceive with callback
    context_cb = await aggregator.perceive(callback_signal)

    assert context_cb.hive.item_identifier == "perceived-honda"
    assert context_cb.hive.offer.bid_amount == 5400.0
    assert context_cb.metadata["source"] == "telegram"

    # 4. Transformer reasoning
    transformer = AuraTransformer(registry)
    reasoning = mocker.Mock(spec=ReasoningSkill)
    reasoning.get_name.return_value = "reasoning"
    reasoning.execute = AsyncMock()
    registry.register("reasoning", reasoning)

    # Mock reasoning to accept
    intent = NegotiationIntent(
        price=5400.0,
        message="Listed!",
        thought="User accepted appraisal."
    )
    any_intent = protobuf.Any()
    any_intent.value = bytes(intent)

    reasoning.execute.return_value = Observation(
        success=True,
        event_type="accept",
        payload=any_intent,
        metadata={}
    )

    decision = await transformer.think(context_cb)

    assert decision.action.name == "ACTION_TYPE_ACCEPT"
    assert decision.negotiation.price == 5400.0
    # Verify vision_result was propagated in metadata
    assert decision.metadata.get("asset_discovered") == "true"
