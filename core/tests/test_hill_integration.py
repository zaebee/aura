import pytest
from unittest.mock import MagicMock
from hive.proteins.guard.skill import GuardSkill
from hive.proteins.guard.engine import OutputGuard
from config.policy import SafetySettings

@pytest.mark.asyncio
async def test_guard_skill_hill_cap_violation():
    skill = GuardSkill()
    settings = SafetySettings(min_profit_margin=0.0)
    skill.bind(settings, OutputGuard(safety_settings=settings))
    await skill.initialize()

    # context: base_price=1000, bid=100.
    # Hill cap will be very close to 100.
    # If LLM suggests 500, it should be a violation.

    obs = await skill.execute(
        "validate_decision",
        {
            "decision": {"action": "counter", "price": 500.0},
            "context": {
                "floor_price": 100.0,
                "internal_cost": 100.0,
                "bid": 100.0,
                "base_price": 1000.0
            },
        },
    )

    assert obs.success is False
    assert "Hill Cap Violation" in obs.error
    assert obs.metadata["error_code"] == "HILL_CAP_VIOLATION"
    # Safe price should be the hill cap
    assert float(obs.metadata["safe_price"]) < 500.0

@pytest.mark.asyncio
async def test_guard_skill_hill_cap_pass():
    skill = GuardSkill()
    settings = SafetySettings(min_profit_margin=0.0)
    skill.bind(settings, OutputGuard(safety_settings=settings))
    await skill.initialize()

    # bid=100, base=1000 -> hill cap ~100 + (900 * 100^2 / (1000^2 + 100^2))
    # ~ 100 + 900 * 10000 / 1010000 ~ 100 + 8.9 ~ 108.9

    obs = await skill.execute(
        "validate_decision",
        {
            "decision": {"action": "counter", "price": 105.0},
            "context": {
                "floor_price": 100.0,
                "internal_cost": 100.0,
                "bid": 100.0,
                "base_price": 1000.0
            },
        },
    )

    assert obs.success is True
