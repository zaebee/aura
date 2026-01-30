import pytest
from guard.membrane import OutputGuard, SafetyViolation


def test_margin_violation():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        "internal_cost": 750.0
    }
    # New Margin = (offered - 750) / offered
    # 0.10 margin requires offered >= 750 / 0.9 = 833.33

    # 800 is below required (800-750)/800 = 0.0625 < 0.10
    decision = {"action": "counter", "price": 800.0}
    with pytest.raises(SafetyViolation, match="Minimum profit margin violation"):
        guard.validate_decision(decision, context)

def test_floor_price_violation_on_accept():
    guard = OutputGuard()
    context = {
        "floor_price": 850.0,
        "internal_cost": 500.0
    }
    # Margin is (840 - 500) / 840 = 0.40 (Good)
    # But price < floor_price

    decision = {"action": "accept", "price": 840.0}
    with pytest.raises(SafetyViolation, match="Floor price violation"):
        guard.validate_decision(decision, context)

def test_floor_price_violation_on_counter():
    guard = OutputGuard()
    context = {
        "floor_price": 850.0,
        "internal_cost": 500.0
    }
    # Counter offer should also respect floor price
    decision = {"action": "counter", "price": 840.0}
    with pytest.raises(SafetyViolation, match="Floor price violation"):
        guard.validate_decision(decision, context)

def test_safe_decision():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        "internal_cost": 700.0
    }
    # min_margin is 0.10.
    # (850 - 700) / 850 = 0.176 > 0.10 (Good)
    # 850 > 800 (Good)

    decision = {"action": "accept", "price": 850.0}
    assert guard.validate_decision(decision, context) is True

def test_invalid_price():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 700.0}

    decision = {"action": "accept", "price": 0.0}
    with pytest.raises(SafetyViolation, match="Invalid offered price"):
        guard.validate_decision(decision, context)
