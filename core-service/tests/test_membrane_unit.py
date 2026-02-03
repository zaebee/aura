import pytest
from src.guard.membrane import OutputGuard, SafetyViolation


def test_margin_violation():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 750.0}
    # New Margin = (offered - 750) / 750
    # 0.10 margin requires offered >= 750 * 1.1 = 825

    # 800 is below required (800-750)/750 = 0.066 < 0.10
    decision = {"action": "counter", "price": 800.0}
    with pytest.raises(SafetyViolation, match="Economic suicide attempt"):
        guard.validate_decision(decision, context)


def test_floor_price_violation_on_accept():
    guard = OutputGuard()
    context = {"floor_price": 850.0, "internal_cost": 500.0}
    # Margin is (840 - 500) / 500 = 0.68 (Good)
    # But price < floor_price

    decision = {"action": "accept", "price": 840.0}
    with pytest.raises(SafetyViolation, match="Floor price breach"):
        guard.validate_decision(decision, context)


def test_floor_price_pass_on_counter():
    guard = OutputGuard()
    context = {"floor_price": 850.0, "internal_cost": 500.0}
    # Counter offer below floor price but above margin should pass according to new logic
    decision = {"action": "counter", "price": 840.0}
    assert guard.validate_decision(decision, context) is True


def test_safe_decision():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 700.0}
    # min_margin is 0.10.
    # (850 - 700) / 850 = 0.176 > 0.10 (Good)
    # 850 > 800 (Good)

    decision = {"action": "accept", "price": 850.0}
    assert guard.validate_decision(decision, context) is True


def test_invalid_price():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 700.0}

    decision = {"action": "accept", "price": 0.0}
    # Price 0.0 will trigger margin violation: (0 - 700) / 700 = -1.0 < 0.10
    with pytest.raises(SafetyViolation, match="Economic suicide attempt"):
        guard.validate_decision(decision, context)


def test_max_discount_violation():
    guard = OutputGuard()
    context = {"base_price": 1000.0, "floor_price": 600.0, "internal_cost": 500.0}
    # Max discount is 0.30, so price must be >= 700
    decision = {"action": "counter", "price": 650.0}
    with pytest.raises(SafetyViolation, match="Maximum discount exceeded"):
        guard.validate_decision(decision, context)


def test_unauthorized_addon():
    guard = OutputGuard()
    context = {"base_price": 1000.0, "floor_price": 600.0, "internal_cost": 500.0}
    decision = {
        "action": "counter",
        "price": 800.0,
        "addons": ["Free Helicopter Ride"],
    }
    with pytest.raises(SafetyViolation, match="Unauthorized addon: Free Helicopter Ride"):
        guard.validate_decision(decision, context)
