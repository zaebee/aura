from unittest.mock import AsyncMock, patch

import pytest
from aura_core.gen.aura.assets import v1 as asset_pb2
from hive.proteins.perception.engine import PerceptionEngine
from hive.proteins.perception.skill import PerceptionSkill

from config.perception import PerceptionSettings


@pytest.fixture
def perception_settings():
    return PerceptionSettings(ollama_url="http://mock:11434", model="gemma3:latest")


@pytest.fixture
def perception_engine(perception_settings):
    return PerceptionEngine(
        ollama_url=perception_settings.ollama_url, model=perception_settings.model
    )


@pytest.mark.asyncio
async def test_perception_skill_execute(perception_settings, perception_engine):
    skill = PerceptionSkill()
    skill.bind(perception_settings, perception_engine)

    mock_item = {
        "id": "perceived-123",
        "make": "Tesla",
        "model": "Model 3",
        "year": 2024,
        "base_price": 40000.0,
        "floor_price": 35000.0,
        "confidence_score": 0.95
    }

    with patch.object(
        perception_engine, "perceive_image", new_callable=AsyncMock
    ) as mock_perceive:
        mock_perceive.return_value = mock_item

        obs = await skill.execute("perceive_image", {"image_bytes": b"fake_image"})

        assert obs.success is True

        # Unpack payload
        asset = asset_pb2.Asset().parse(obs.payload.value)
        assert asset.identifier == "perceived-123"
        assert asset.vehicle.brand == "Tesla"
        assert asset.rental_terms.price_tiers[0].price_per_day == 40000.0


@pytest.mark.asyncio
async def test_perception_engine_mapping(perception_engine):
    raw_response = """
    {
        "make": "Tesla",
        "model": "Model 3",
        "year": 2024,
        "color": "Red",
        "estimated_price": 45000.0,
        "confidence_score": 0.95
    }
    """
    item = perception_engine._parse_and_validate(raw_response)
    assert item["name"] == "2024 Tesla Model 3"
    assert item["base_price"] == 45000.0
    assert item["meta"]["color"] == "Red"
