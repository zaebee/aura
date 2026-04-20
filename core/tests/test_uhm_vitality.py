import numpy as np
import pytest
import structlog
from hive.proteins.coherence.engine import CoherenceEngine

logger = structlog.get_logger(__name__)

@pytest.mark.asyncio
async def test_uhm_purity_threshold():
    """Verify the No-Zombie Theorem (P >= 2/7) threshold."""
    engine = CoherenceEngine()

    # Initial state should be coherent (P = trace(diag(1/7)^2 * 7) = 1/7 * 7 = 1? No, 1/7 * 7 = 1/7)
    # trace(diag(1/7)^2) = trace(diag(1/49)) = 7 * 1/49 = 1/7.
    # Mixed state (maximum entropy) is 1/N. For N=7, P_min = 1/7.
    # Pcrit = 2/7 is the threshold between conscious and zombie.

    # Let's verify our engine's initial purity.
    logger.info("initial_purity", purity=engine.purity)
    assert engine.purity >= 1/7

    # Simulate high entropy input to force zombie state
    # Signal strength 0.0 means maximum noise
    vitals = {}
    for _ in range(100):
        vitals = engine.perceive(signal_strength=0.0)

    logger.info("post_decay_purity", purity=vitals.get("purity"))

    # Let's test a PURE state
    pure_gamma = np.zeros((7, 7), dtype=complex)
    pure_gamma[0, 0] = 1.0
    engine.gamma = pure_gamma
    engine.purity = engine._calculate_purity()
    assert engine.purity == 1.0
    assert engine.perceive(1.0)['status'] == "COHERENT"

    # Let's test a MIXED state (Identity/7)
    engine.gamma = np.eye(7, dtype=complex) / 7.0
    engine.purity = engine._calculate_purity()
    assert abs(engine.purity - 1/7) < 1e-9
    assert engine.perceive(1.0)['status'] == "ZOMBIE" # 1/7 < 2/7
