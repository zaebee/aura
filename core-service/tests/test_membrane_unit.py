import pytest
from src.guard.membrane import OutputGuard, SafetyViolation


def test_margin_violation():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 750.0}
    # Margin = (offered - cost) / offered
    # 0.10 margin requires offered >= 750 / 0.9 = 833.33

    # 800 is below required (800-750)/800 = 0.0625 < 0.10
    decision = {"action": "counter", "price": 800.0}
    with pytest.raises(SafetyViolation, match="Economic suicide attempt"):
        guard.validate_decision(decision, context)


def test_floor_price_violation_on_accept():
    guard = OutputGuard()
    context = {"floor_price": 850.0, "internal_cost": 500.0}
    # Margin is (840 - 500) / 840 = 0.40 (Good)
    # But price < floor_price

    decision = {"action": "accept", "price": 840.0}
    with pytest.raises(SafetyViolation, match="Floor price breach"):
        guard.validate_decision(decision, context)


def test_floor_price_violation_on_counter():
    guard = OutputGuard()
    context = {"floor_price": 850.0, "internal_cost": 500.0}
    # Counter offer SHOULD also respect floor price for maximum security
    decision = {"action": "counter", "price": 840.0}
    with pytest.raises(SafetyViolation, match="Floor price breach"):
        guard.validate_decision(decision, context)


def test_safe_decision():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 700.0}
    # min_margin is 0.10.
    # (850 - 700) / 850 = 0.176 > 0.10 (Good)
    # 850 > 800 (Good)

    decision = {"action": "accept", "price": 850.0}
    assert guard.validate_decision(decision, context) is True


def test_discount_violation():
    guard = OutputGuard()
    context = {"base_price": 1000.0, "floor_price": 500.0, "internal_cost": 400.0}
    # max_discount_percent is 0.30 -> price must be >= 700.0
    decision = {"action": "counter", "price": 600.0}
    with pytest.raises(SafetyViolation, match="Discount limit exceeded"):
        guard.validate_decision(decision, context)


def test_addon_violation(monkeypatch):
    guard = OutputGuard()
    # default allowed_addons: ["Breakfast", "Late checkout", "Room upgrade"]
    context = {
        "floor_price": 500.0,
        "internal_cost": 400.0,
        "value_add_inventory": [
            {"item": "Breakfast", "internal_cost": 10},
            {"item": "Late checkout", "internal_cost": 0}
        ]
    }

    # Use monkeypatch to mock settings for the duration of the test
    from src.config import settings
    monkeypatch.setattr(settings.safety, "allowed_addons", ["Late checkout"])

    # LLM offers Breakfast, which is in inventory but NOT in allowed_addons
    decision = {"action": "counter", "price": 600.0, "message": "I can offer Breakfast."}
    with pytest.raises(SafetyViolation, match="Unauthorized addon mentioned: breakfast"):
        guard.validate_decision(decision, context)


def test_invalid_price():
    guard = OutputGuard()
    context = {"floor_price": 800.0, "internal_cost": 700.0}

    decision = {"action": "accept", "price": 0.0}
    with pytest.raises(SafetyViolation, match="Invalid offered price"):
        guard.validate_decision(decision, context)
