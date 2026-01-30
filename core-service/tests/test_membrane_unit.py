import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from guard.membrane import OutputGuard, SafetyViolation

def test_margin_violation():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        "internal_cost": 750.0  # Margin = (offered - 750) / 750
    }
    # 0.10 margin of 750 is 75. So offered price must be >= 750 + 75 = 825

    # This should fail (margin = (800 - 750) / 750 = 0.066 < 0.10)
    decision = {"action": "counter", "price": 800.0}
    with pytest.raises(SafetyViolation, match="Economic suicide attempt"):
        guard.validate_decision(decision, context)

def test_floor_price_breach():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        "internal_cost": 500.0
    }
    # Margin is (750 - 500) / 500 = 0.5 (Good)
    # But price < floor_price and action is accept

    decision = {"action": "accept", "price": 750.0}
    with pytest.raises(SafetyViolation, match="Floor price breach"):
        guard.validate_decision(decision, context)

def test_safe_decision():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        "internal_cost": 700.0
    }
    # min_margin is 0.10.
    # (850 - 700) / 700 = 0.214 > 0.10 (Good)
    # 850 > 800 (Good)

    decision = {"action": "accept", "price": 850.0}
    assert guard.validate_decision(decision, context) is True

def test_missing_internal_cost():
    guard = OutputGuard()
    context = {
        "floor_price": 800.0,
        # missing internal_cost
    }
    # Should log warning but not raise error if internal_cost is 0 or missing,
    # UNLESS it's a floor price breach

    decision = {"action": "accept", "price": 850.0}
    assert guard.validate_decision(decision, context) is True

    decision_fail = {"action": "accept", "price": 750.0}
    with pytest.raises(SafetyViolation, match="Floor price breach"):
        guard.validate_decision(decision_fail, context)
