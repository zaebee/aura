import pytest
from src.guard.membrane import OutputGuard, SafetyViolation


def test_margin_violation():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 750.0}
    # Margin (Markup) = (offered - 750) / 750
    # 0.10 margin requires offered >= 750 * 1.1 = 825

    # 800 is below required: (800-750)/750 = 0.066 < 0.10
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


def test_floor_price_bypass_on_counter():
    guard = OutputGuard()
    context = {"floor_price": 850.0, "internal_cost": 500.0}
    # According to new logic, only 'accept' is blocked by floor_price.
    # 'counter' is allowed as long as margin is safe.
    decision = {"action": "counter", "price": 840.0}
    assert guard.validate_decision(decision, context) is True


def test_discount_violation():
    guard = OutputGuard()
    context = {"base_price": 1000.0, "floor_price": 500.0, "internal_cost": 400.0}
    # max_discount_percent is 0.30.
    # Price 600. Discount = (1000 - 600) / 1000 = 0.40 > 0.30.
    decision = {"action": "counter", "price": 600.0}
    with pytest.raises(SafetyViolation, match="Excessive discount attempt"):
        guard.validate_decision(decision, context)


def test_addon_violation():
    guard = OutputGuard()
    context = {"base_price": 1000.0, "floor_price": 500.0, "internal_cost": 400.0}
    # Allowed addons: "Breakfast", "Late checkout", "Room upgrade"
    decision = {"action": "counter", "price": 900.0, "addons": ["Champagne"]}
    with pytest.raises(SafetyViolation, match="Unauthorized addon: Champagne"):
        guard.validate_decision(decision, context)


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
    with pytest.raises(SafetyViolation, match="Invalid offered price"):
        guard.validate_decision(decision, context)
