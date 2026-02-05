import pytest
from hive.proteins.guard.main import GuardSkill

from config.policy import SafetySettings


@pytest.mark.asyncio
async def test_guard_skill_initialize():
    skill = GuardSkill()
    settings = SafetySettings()
    success = await skill.initialize(settings)
    assert success is True
    assert skill.settings == settings


@pytest.mark.asyncio
async def test_guard_skill_validate_decision():
    skill = GuardSkill()
    await skill.initialize(SafetySettings(min_profit_margin=0.1))

    # Valid decision
    obs = await skill.execute(
        "validate_decision",
        {
            "decision": {"action": "accept", "price": 100.0},
            "context": {"floor_price": 50.0, "internal_cost": 50.0},
        },
    )
    assert obs.success is True

    # Invalid decision (below floor)
    obs2 = await skill.execute(
        "validate_decision",
        {
            "decision": {"action": "accept", "price": 40.0},
            "context": {"floor_price": 50.0, "internal_cost": 30.0},
        },
    )
    assert obs2.success is False
    assert "floor" in obs2.error.lower()
