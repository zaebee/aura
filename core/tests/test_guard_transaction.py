"""
Tests for CRISPR Rules A + B — Guard validate_transaction.
Phase B: Immune System Hardening.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.metabolism.math import HillDampener
from aura_hive.hive.proteins.guard.engine import OutputGuard, SafetyViolation
from aura_hive.hive.proteins.guard.skill import GuardSkill


def _make_skill() -> GuardSkill:
    skill = GuardSkill()
    settings = SafetySettings()
    skill.bind(settings, OutputGuard(safety_settings=settings))
    return skill


# ── engine-level tests ──────────────────────────────────────────────────────


def test_validate_transaction_unsanctified_raises():
    """Rule A: SafetyViolation when wallet is not sanctified."""
    guard = OutputGuard(safety_settings=SafetySettings())
    with pytest.raises(SafetyViolation, match="not sanctified"):
        guard.validate_transaction(
            wallet_address="0xBAD",
            llm_price=100.0,
            bid=80.0,
            base_price=120.0,
            is_sanctified=False,
        )


def test_validate_transaction_applies_hill_cap():
    """Rule B: price is capped at the Hill-dampened ceiling."""
    guard = OutputGuard(safety_settings=SafetySettings())
    bid = 80.0
    base_price = 120.0
    llm_price = 200.0  # Way above ceiling

    safe_price = guard.validate_transaction(
        wallet_address="0xGOOD",
        llm_price=llm_price,
        bid=bid,
        base_price=base_price,
        is_sanctified=True,
    )

    expected_ceiling = HillDampener.hill_cap(bid, base_price)
    assert safe_price == min(llm_price, expected_ceiling)
    assert safe_price < llm_price  # should be capped


def test_validate_transaction_sanctified_passes():
    """Happy path: sanctified wallet with reasonable LLM price returns safe price."""
    guard = OutputGuard(safety_settings=SafetySettings())
    bid = 100.0
    base_price = 100.0
    llm_price = 100.0

    safe_price = guard.validate_transaction(
        wallet_address="0xGOOD",
        llm_price=llm_price,
        bid=bid,
        base_price=base_price,
        is_sanctified=True,
    )

    # When bid == base_price, Hill cap == base_price; llm_price == base_price → no capping
    assert safe_price == llm_price


# ── skill-level tests ───────────────────────────────────────────────────────


def test_guard_skill_inject_registry():
    """inject_registry stores the registry reference."""
    skill = _make_skill()
    assert skill._registry is None

    mock_registry = MagicMock()
    skill.inject_registry(mock_registry)
    assert skill._registry is mock_registry


@pytest.mark.asyncio
async def test_guard_skill_validate_transaction_capability():
    """validate_transaction capability is present and dispatches correctly."""
    skill = _make_skill()

    # Mock registry returning sanctified = True
    mock_registry = MagicMock()
    mock_obs = MagicMock(success=True)
    mock_obs.metadata.to_dict.return_value = {"sanctified": True}
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
    # registry was queried for sanctification
    mock_registry.execute.assert_called_once_with(
        "persistence", "is_wallet_sanctified", {"wallet_address": "0xGOOD"}
    )


# ── x402 payment tests ───────────────────────────────────────────────────────


def test_validate_x402_payment_unsanctified_raises():
    """x402 payment to unsanctified wallet raises SafetyViolation."""
    guard = OutputGuard(safety_settings=SafetySettings())
    with pytest.raises(SafetyViolation, match="not sanctified"):
        guard.validate_x402_payment(
            wallet_address="0xBAD",
            amount=1.0,
            is_sanctified=False,
        )


def test_validate_x402_payment_over_cap_raises():
    """x402 payment exceeding max_x402_payment cap raises SafetyViolation."""
    settings = SafetySettings(max_x402_payment=5.0)
    guard = OutputGuard(safety_settings=settings)
    with pytest.raises(SafetyViolation, match="exceeds spending cap"):
        guard.validate_x402_payment(
            wallet_address="0xGOOD",
            amount=10.0,
            is_sanctified=True,
        )


def test_validate_x402_payment_within_cap_passes():
    """x402 payment within cap for sanctified wallet passes without raising."""
    settings = SafetySettings(max_x402_payment=5.0)
    guard = OutputGuard(safety_settings=settings)
    guard.validate_x402_payment(
        wallet_address="0xGOOD",
        amount=0.05,
        is_sanctified=True,
    )


@pytest.mark.asyncio
async def test_guard_skill_validate_x402_payment_unsanctified_blocked():
    """validate_x402_payment blocks unsanctified recipient."""
    skill = _make_skill()

    mock_registry = MagicMock()
    mock_obs = MagicMock(success=True)
    mock_obs.metadata.to_dict.return_value = {"sanctified": False}
    mock_registry.execute = AsyncMock(return_value=mock_obs)
    skill.inject_registry(mock_registry)

    obs = await skill.execute(
        "validate_x402_payment",
        {"wallet_address": "0xBAD", "amount": 1.0},
    )

    assert obs.success is False
    assert "not sanctified" in obs.error


@pytest.mark.asyncio
async def test_guard_skill_validate_x402_payment_over_cap_blocked():
    """validate_x402_payment blocks payments over the spending cap."""
    skill = GuardSkill()
    settings = SafetySettings(max_x402_payment=5.0)
    skill.bind(settings, OutputGuard(safety_settings=settings))

    mock_registry = MagicMock()
    mock_obs = MagicMock(success=True)
    mock_obs.metadata.to_dict.return_value = {"sanctified": True}
    mock_registry.execute = AsyncMock(return_value=mock_obs)
    skill.inject_registry(mock_registry)

    obs = await skill.execute(
        "validate_x402_payment",
        {"wallet_address": "0xGOOD", "amount": 100.0},
    )

    assert obs.success is False
    assert "exceeds spending cap" in obs.error


@pytest.mark.asyncio
async def test_guard_skill_validate_x402_payment_happy_path():
    """validate_x402_payment passes for sanctified wallet within cap."""
    skill = GuardSkill()
    settings = SafetySettings(max_x402_payment=5.0)
    skill.bind(settings, OutputGuard(safety_settings=settings))

    mock_registry = MagicMock()
    mock_obs = MagicMock(success=True)
    mock_obs.metadata.to_dict.return_value = {"sanctified": True}
    mock_registry.execute = AsyncMock(return_value=mock_obs)
    skill.inject_registry(mock_registry)

    obs = await skill.execute(
        "validate_x402_payment",
        {"wallet_address": "0xGOOD", "amount": 0.05},
    )

    assert obs.success is True
