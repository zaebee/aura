from aura_hive.hive.metabolism.math import HillDampener


def test_hill_cap_bid_equals_base_price() -> None:
    # bid == base_price: saturation = 0.5, ceiling = bid + gap*0.5 = base_price
    result = HillDampener.hill_cap(1000.0, 1000.0)
    assert result == 1000.0


def test_hill_cap_bid_zero_returns_bid() -> None:
    result = HillDampener.hill_cap(0.0, 1000.0)
    assert result == 0.0


def test_hill_cap_base_price_zero_returns_bid() -> None:
    result = HillDampener.hill_cap(500.0, 0.0)
    assert result == 500.0


def test_hill_cap_bid_much_less_than_base() -> None:
    # bid=100, base=1000 → saturation = 100^2/(1000^2+100^2) ≈ 0.0099
    # ceiling ≈ 100 + 900*0.0099 ≈ 108.91, well below base_price
    result = HillDampener.hill_cap(100.0, 1000.0)
    assert result < 200.0
    assert result > 100.0


def test_hill_cap_bid_half_of_base() -> None:
    # bid=500, base=1000 → saturation = 500^2/(1000^2+500^2) = 250000/1250000 = 0.2
    # ceiling = 500 + 500*0.2 = 600.0
    result = HillDampener.hill_cap(500.0, 1000.0)
    assert result == 600.0


def test_apply_caps_greedy_price() -> None:
    cap = HillDampener.hill_cap(700.0, 1000.0)
    result = HillDampener.apply(1200.0, 700.0, 1000.0)
    assert result <= cap


def test_apply_returns_llm_price_when_already_below_cap() -> None:
    # llm_price=750 is below hill_cap(700, 1000) ≈ 849
    result = HillDampener.apply(750.0, 700.0, 1000.0)
    assert result == 750.0


def test_apply_with_zero_bid_returns_llm_price() -> None:
    # Safe fallback: when bid is unknown (zero), do not dampen
    result = HillDampener.apply(1200.0, 0.0, 1000.0)
    assert result == 1200.0
