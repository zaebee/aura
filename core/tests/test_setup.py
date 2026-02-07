import pytest
from metabolism_setup import setup_metabolism
from aura_core import MetabolicLoop, SkillRegistry

@pytest.mark.asyncio
async def test_setup_metabolism():
    metabolism, registry, market_service = await setup_metabolism()
    assert isinstance(metabolism, MetabolicLoop)
    assert isinstance(registry, SkillRegistry)
    # Check that skills are registered
    assert registry.get("persistence") is not None
    assert registry.get("reasoning") is not None
    assert registry.get("telemetry") is not None
    assert registry.get("pulse") is not None
    assert registry.get("guard") is not None
