"""
Holonom v3.0: Quantum Regeneration & 7-Dimensional Metabolism (UHM-Native).
"""

from datetime import UTC, datetime
from typing import Any

import numpy as np
import structlog

from config import get_settings

from .errors import ApoptosisTrigger, GeometricCeilingError

logger = structlog.get_logger(__name__)


class HolonomV3:
    """
    Quantum Holonom implementation for Project "Queen Bee" v3.0.
    """

    DIMENSIONS = ["A", "S", "D", "L", "E", "O", "U"]

    def __init__(self, kappa_0: float = 1.0):
        settings = get_settings().metabolism
        self.pcrit = settings.pcrit
        self.sad_max = settings.sad_max
        self.kappa_boot = settings.kappa_boot
        self.sigma_k_max = settings.sigma_k_max

        # Initialize complex coherence matrix from configurable diagonal
        # This ensures initial purity P > pcrit
        diag = np.array(settings.initial_diagonal, dtype=complex)
        self.gamma = np.diag(diag)

        # Ensure trace 1
        trace_val = np.trace(self.gamma)
        if np.abs(trace_val) > 1e-15:
            self.gamma /= trace_val

        self.purity = self._calculate_purity()
        self.kappa_0 = kappa_0
        self.recursion_depth = 0

    def _calculate_purity(self) -> float:
        """P = trace(Γ²)"""
        return float(np.real(np.trace(np.dot(self.gamma, self.gamma))))

    def get_stress_tensor(self) -> np.ndarray:
        """
        Calculate stress tensor σk = clamp(1 - 7γkk, 0, 1)
        """
        diagonals = np.real(np.diag(self.gamma))
        sigma = np.clip(1.0 - 7.0 * diagonals, 0.0, 1.0)
        return sigma

    def calculate_regeneration(self) -> float:
        """
        Quantum regeneration κ = κ_boot + κ0 * CohE
        """
        coh_e = float(np.real(self.gamma[4, 4]))
        kappa = self.kappa_boot + self.kappa_0 * coh_e
        return kappa

    def verify_viability(self) -> None:
        """
        Enforce the Viability Gate.
        """
        if self.purity < self.pcrit:
            logger.error(
                "viability_gate_failure", purity=self.purity, threshold=self.pcrit
            )
            raise ApoptosisTrigger("Critical loss of coherence: P < 2/7")

    def track_self_modeling(self, increment: int = 1) -> None:
        """
        Track self-modeling recursion depth (SAD_MAX).
        """
        self.recursion_depth += increment
        if self.recursion_depth > self.sad_max:
            logger.error("geometric_ceiling_exceeded", depth=self.recursion_depth)
            raise GeometricCeilingError(
                f"Recursion depth {self.recursion_depth} exceeds SADmax={self.sad_max}"
            )

    def reset_recursion(self) -> None:
        self.recursion_depth = 0

    def step(
        self, internal_experience: float, external_signals: np.ndarray
    ) -> dict[str, Any]:
        """
        Perform one metabolic step.
        """
        self.gamma[4, 4] = np.clip(self.gamma[4, 4] + internal_experience * 0.1, 0, 1)
        for i, val in enumerate(external_signals[:7]):
            self.gamma[i, i] = np.clip(self.gamma[i, i] + val * 0.05, 0, 1)
        trace_val = np.trace(self.gamma)
        if np.abs(trace_val) > 1e-15:
            self.gamma /= trace_val
        self.purity = self._calculate_purity()
        sigma = self.get_stress_tensor()
        kappa = self.calculate_regeneration()
        self.verify_viability()
        if np.any(sigma > self.sigma_k_max):
            logger.info("stress_induced_regeneration_triggered", sigma=sigma)
            self.gamma += np.eye(7) * (kappa * 0.01)
            self.gamma /= np.trace(self.gamma)
            self.purity = self._calculate_purity()

        return {
            "purity": self.purity,
            "stress_tensor": sigma.tolist(),
            "regeneration_kappa": kappa,
            "timestamp": datetime.now(UTC).isoformat(),
        }
