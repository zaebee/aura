import numpy as np
import pytest
from hive.chemistry.hill_regulator import HillRegulator
from hive.metabolism.errors import ApoptosisTrigger, GeometricCeilingError
from hive.metabolism.holonom_v3 import HolonomV3


def test_hill_regulator_n_2_8():
    """Verify Hill Equation with n=2.8."""
    reg = HillRegulator()
    assert reg.HILL_N == 2.8

    # At usage = threshold, dampening should be 0.5
    dampening = reg.calculate_dampening(100, 100)
    assert abs(dampening - 0.5) < 1e-7

    # High usage should dampen heavily
    dampening_high = reg.calculate_dampening(200, 100)
    assert dampening_high < 0.5

    # Low usage should dampen lightly
    dampening_low = reg.calculate_dampening(50, 100)
    assert dampening_low > 0.5


def test_holonom_v3_dimensions():
    """Verify ASDLEOU dimensions and matrix init."""
    holonom = HolonomV3()
    assert holonom.gamma.shape == (7, 7)
    assert abs(np.trace(holonom.gamma) - 1.0) < 1e-9
    # Initial purity for identity/7 is 1/7
    assert abs(holonom.purity - 1 / 7) < 1e-9


def test_holonom_v3_stress_tensor():
    """Verify sigma_k calculation."""
    holonom = HolonomV3()
    # Initial diag is [1/7, ..., 1/7]
    # sigma_k = 1 - 7*(1/7) = 0
    sigma = holonom.get_stress_tensor()
    assert np.all(sigma == 0.0)

    # Set one diag to 0
    holonom.gamma[0, 0] = 0.0
    sigma = holonom.get_stress_tensor()
    assert sigma[0] == 1.0


def test_holonom_v3_regeneration():
    """Verify kappa calculation and coh_e dependency."""
    holonom = HolonomV3()
    # kappa = 5.71 + 1.0 * (1/7)
    expected = 5.71 + 1.0 / 7.0
    assert abs(holonom.calculate_regeneration() - expected) < 1e-9


def test_goldilocks_zone_and_viability():
    """Verify Purity limits and Viability Gate."""
    holonom = HolonomV3()

    # Pcrit = 2/7 ≈ 0.2857
    # Identity/7 purity is 1/7 ≈ 0.1428 (ZOMBIE)
    with pytest.raises(ApoptosisTrigger):
        holonom.verify_viability()

    # Make it pure (P=1.0)
    holonom.gamma = np.zeros((7, 7), dtype=complex)
    holonom.gamma[0, 0] = 1.0
    holonom.purity = holonom._calculate_purity()
    holonom.verify_viability()  # Should pass

    # Test Goldilocks range (0.286, 0.428]
    # We can simulate a state in Goldilocks
    # P = trace(diag(p1...p7)^2)
    # If p1=0.5, p2=0.5, others=0, P = 0.25 + 0.25 = 0.5 (Above 0.428)
    # If p1=0.4, p2=0.3, p3=0.3, P = 0.16 + 0.09 + 0.09 = 0.34 (In Goldilocks)
    holonom.gamma = np.diag([0.4, 0.3, 0.3, 0.0, 0.0, 0.0, 0.0]).astype(complex)
    holonom.purity = holonom._calculate_purity()
    assert 0.286 < holonom.purity <= 0.428


def test_sad_ceiling():
    """Verify SADmax = 3 recursion limit."""
    holonom = HolonomV3()
    holonom.track_self_modeling(1)
    holonom.track_self_modeling(1)
    holonom.track_self_modeling(1)
    with pytest.raises(GeometricCeilingError):
        holonom.track_self_modeling(1)


@pytest.mark.asyncio
async def test_metabolic_step():
    """Verify one metabolic step in HolonomV3."""
    holonom = HolonomV3()
    # Force a viable state first
    holonom.gamma = np.diag([0.4, 0.3, 0.3, 0.0, 0.0, 0.0, 0.0]).astype(complex)

    signals = np.zeros(7)
    stats = holonom.step(internal_experience=0.5, external_signals=signals)

    assert "purity" in stats
    assert "stress_tensor" in stats
    assert "regeneration_kappa" in stats
