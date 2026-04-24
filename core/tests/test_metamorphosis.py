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


def test_hill_regulator_initialization():
    """Verify Hill Equation initialization."""
    reg = HillRegulator()
    # Default is 2.8 from MetabolismSettings
    assert reg.hill_n == 2.8

    reg_custom = HillRegulator(coefficient=3.5)
    assert reg_custom.hill_n == 3.5


def test_hill_regulator_affinity():
    """Verify affinity calculation."""
    reg = HillRegulator(coefficient=2.8)
    # Test affinity: high stress (1.0) -> low affinity (< 0.1)
    assert reg.compute_affinity(1.0) < 0.1
    # Low stress (0.0) -> high affinity
    assert reg.compute_affinity(0.0) == 1.0


def test_holonom_v3_dimensions():
    """Verify ASDLEOU dimensions and matrix init."""
    holonom = HolonomV3()
    assert holonom.gamma.shape == (7, 7)
    assert abs(np.trace(holonom.gamma) - 1.0) < 1e-9
    # Initial purity is now > 0.2857 (pcrit) as per configurable diagonal
    assert holonom.purity > 0.2857


def test_holonom_v3_stress_tensor():
    """Verify sigma_k calculation."""
    holonom = HolonomV3()
    # sigma_k = clamp(1 - 7*gamma_kk, 0, 1)
    sigma = holonom.get_stress_tensor()
    # Check that it returns 7 values
    assert len(sigma) == 7

    # Manually set one diag to 1/7
    holonom.gamma[0, 0] = 1.0 / 7.0
    # Re-calc stress
    sigma = holonom.get_stress_tensor()
    assert abs(sigma[0]) < 1e-9


def test_holonom_v3_regeneration():
    """Verify kappa calculation and coh_e dependency."""
    holonom = HolonomV3()
    # kappa = kappa_boot + kappa_0 * CohE
    # CohE is diagonal element at index 4
    coh_e = float(np.real(holonom.gamma[4, 4]))
    expected = 5.71 + 1.0 * coh_e
    assert abs(holonom.calculate_regeneration() - expected) < 1e-9


def test_goldilocks_zone_and_viability():
    """Verify Viability Gate."""
    holonom = HolonomV3()

    # Should pass by default now
    holonom.verify_viability()

    # Force failure
    holonom.gamma = np.eye(7, dtype=complex) / 7.0
    holonom.purity = holonom._calculate_purity()
    with pytest.raises(ApoptosisTrigger):
        holonom.verify_viability()


def test_sad_ceiling():
    """Verify SADmax recursion limit."""
    holonom = HolonomV3()
    # sad_max is 3
    holonom.track_self_modeling(1)
    holonom.track_self_modeling(1)
    holonom.track_self_modeling(1)
    with pytest.raises(GeometricCeilingError):
        holonom.track_self_modeling(1)


@pytest.mark.asyncio
async def test_metabolic_step():
    """Verify one metabolic step in HolonomV3."""
    holonom = HolonomV3()
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
    # sigma_O = 1 - 7*p5.
    gamma_stressed = np.diag([0.94, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]).astype(complex)
    # P = 0.94^2 + 6*0.01^2 = 0.8836 + 0.0006 = 0.8842 > 0.2857
    with pytest.raises(MetabolicError) as exc:
        synth.execute(gamma_stressed, {"data": "nectar"})
    assert "ресурсного стресса" in str(exc.value)

    # 3. Test Nu-monitoring and adaptive rigor
    gamma_healthy = np.diag([0.6, 0.1, 0.06, 0.06, 0.06, 0.06, 0.06]).astype(complex)
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
