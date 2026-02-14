"""Tests for CRISPR Rules A + B — Guard validate_transaction. Phase B."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from hive.metabolism.math import HillDampener
from hive.proteins.guard.engine import OutputGuard, SafetyViolation
from hive.proteins.guard.skill import GuardSkill

from config.policy import SafetySettings


def _make_skill() -> GuardSkill:
    skill = GuardSkill()
    settings = SafetySettings()
    skill.bind(settings, OutputGuard(safety_settings=settings))
    return skill


def test_validate_transaction_unsanctified_raises() -> None:
    guard = OutputGuard(safety_settings=SafetySettings())
    with pytest.raises(SafetyViolation, match="not sanctified"):
        guard.validate_transaction("0xBAD", 100.0, 80.0, 120.0, False)


def test_validate_transaction_applies_hill_cap() -> None:
    guard = OutputGuard(safety_settings=SafetySettings())
    bid, base_price, llm_price = 80.0, 120.0, 200.0
    safe_price = guard.validate_transaction("0xGOOD", llm_price, bid, base_price, True)
    assert safe_price < llm_price
    assert safe_price == min(llm_price, HillDampener.hill_cap(bid, base_price))


def test_validate_transaction_sanctified_passes() -> None:
    guard = OutputGuard(safety_settings=SafetySettings())
    safe_price = guard.validate_transaction("0xGOOD", 100.0, 100.0, 100.0, True)
    assert safe_price == 100.0


def test_guard_skill_inject_registry() -> None:
    skill = _make_skill()
    assert skill._registry is None
    mock_registry = MagicMock()
    skill.inject_registry(mock_registry)
    assert skill._registry is mock_registry


@pytest.mark.asyncio
async def test_guard_skill_validate_transaction_capability() -> None:
    skill = _make_skill()
    from aura_core_gen.aura.core.google import protobuf
    from aura_core_gen.aura.core.v1 import Observation

    mock_registry = MagicMock()
    mock_obs = Observation(
        success=True, metadata=protobuf.Struct().from_dict({"sanctified": True})
    )
    mock_registry.execute = AsyncMock(return_value=mock_obs)
    skill.inject_registry(mock_registry)
    obs = await skill.execute(
        "validate_transaction",
        {
            "wallet_address": "0xGOOD",
            "llm_price": 90.0,
            "bid": 80.0,
            "base_price": 120.0,
        },
    )
    assert obs.success is True
    assert "safe_price" in obs.metadata.to_dict()
    mock_registry.execute.assert_called_once_with(
        "persistence", "is_wallet_sanctified", {"wallet_address": "0xGOOD"}
    )
