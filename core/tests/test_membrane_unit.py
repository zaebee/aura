from unittest.mock import MagicMock

import pytest
from src.hive.proteins.guard.enzymes.guard_logic import OutputGuard, SafetyViolation


def test_output_guard_validate_decision_accept_above_floor():
    guard = OutputGuard(safety_settings=MagicMock(min_profit_margin=0.1))
    decision = {"action": "accept", "price": 120.0}
    context = {"floor_price": 100.0, "internal_cost": 90.0}
    # (120 - 90) / 120 = 0.25 > 0.1
    assert guard.validate_decision(decision, context) is True


def test_output_guard_validate_decision_below_floor():
    guard = OutputGuard(safety_settings=MagicMock(min_profit_margin=0.1))
    decision = {"action": "accept", "price": 90.0}
    context = {"floor_price": 100.0, "internal_cost": 80.0}
    with pytest.raises(SafetyViolation, match="Floor price violation"):
        guard.validate_decision(decision, context)


def test_output_guard_validate_decision_below_margin():
    guard = OutputGuard(safety_settings=MagicMock(min_profit_margin=0.2))
    decision = {"action": "accept", "price": 110.0}
    context = {"floor_price": 100.0, "internal_cost": 100.0}
    # (110 - 100) / 110 = 0.09 < 0.2
    with pytest.raises(SafetyViolation, match="Minimum profit margin violation"):
        guard.validate_decision(decision, context)


def test_output_guard_invalid_price():
    guard = OutputGuard(safety_settings=MagicMock(min_profit_margin=0.1))
    decision = {"action": "accept", "price": -10.0}
    context = {"floor_price": 100.0, "internal_cost": 90.0}
    with pytest.raises(SafetyViolation, match="Invalid offered price"):
        guard.validate_decision(decision, context)
