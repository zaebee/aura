import numpy as np
import pytest
from hive.chemistry.hill_regulator import HillRegulator
from hive.metabolism.errors import (
    ApoptosisTrigger,
    DeathSpiralError,
    GeometricCeilingError,
    MetabolicError,
)
from hive.metabolism.holonom_v3 import HolonomV3
from hive.metabolism.pattern_synthesizer import PatternSynthesizer
from hive.metabolism.theory_interop import Theory, TheorySpace


def test_hill_regulator_n_2_8():
    """Verify Hill Equation with n=2.8."""
    reg = HillRegulator()
    assert reg.HILL_N == 2.8

    # Test affinity: high stress (1.0) -> low affinity (< 0.1)
    assert reg.compute_affinity(1.0) < 0.1
    # Low stress (0.1) -> high affinity
    assert reg.compute_affinity(0.1) > 0.9


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


def test_pattern_synthesizer_v4_logic():
    """Verify PatternSynthesizer correctly reacts to stress, purity, and nu."""
    synth = PatternSynthesizer()

    # 1. Test Death Spiral (low purity)
    gamma_zombie = np.eye(7, dtype=complex) / 7.0
    with pytest.raises(DeathSpiralError):
        synth.execute(gamma_zombie, {"data": "nectar"})

    # 2. Test Resource Stress (sigma_O)
    gamma_stressed = np.diag([0.94, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]).astype(complex)
    with pytest.raises(MetabolicError) as exc:
        synth.execute(gamma_stressed, {"data": "nectar"})
    assert "ресурсного стресса" in str(exc.value)

    # 3. Test Nu-monitoring and adaptive rigor
    gamma_healthy = np.diag([0.7, 0.05, 0.05, 0.05, 0.05, 0.1, 0.0]).astype(complex)
    gamma_healthy /= np.trace(gamma_healthy)

    # Low complexity -> certified rigor
    insight_low = synth.execute(gamma_healthy, {"data": "small"})
    assert insight_low.rigor_mode == "certified"

    # High complexity -> fast rigor
    insight_high = synth.execute(gamma_healthy, {"data": "large" * 1000})
    assert insight_high.rigor_mode == "fast"


def test_theory_interop():
    """Verify theory space immersion and translation."""
    space = TheorySpace()
    t1 = Theory(name="ZFC", foundation="LFnd")
    t2 = Theory(name="HoTT", foundation="LFnd")

    space.load_theory(t1)
    space.load_theory(t2)

    result = space.translate("ZFC", "HoTT", "set_axiom")
    assert "translated(set_axiom)_from_LFnd_to_LFnd" in result

    coherence = space.check_coherence()
    assert coherence == 1.0  # Both are LFnd

    t3 = Theory(name="Classy", foundation="LCls")
    space.load_theory(t3)
    coherence_mixed = space.check_coherence()
    assert coherence_mixed < 1.0  # Mixed foundations
