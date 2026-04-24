"""
Hill Regulator: Cooperative Kinetics for Resource Homeostasis.

Uses the Hill Equation to prevent Memory Famine (OOM)
by dampening processing loads as they approach physical or logical limits.
"""

from typing import Optional

import structlog

from config import get_settings

logger = structlog.get_logger(__name__)


class HillRegulator:
    """
    Bio-digital resource regulator based on the Hill Equation.
    """

    def __init__(self, coefficient: Optional[float] = None):
        settings = get_settings()
        self.hill_n = coefficient if coefficient is not None else settings.metabolism.hill_n

    @classmethod
    def calculate_dampening(cls, current_usage: float, threshold: float, n: float = 2.8) -> float:
        """
        Calculate dampening factor [0, 1].
        """
        if threshold <= 0:
            return 0.0
        if current_usage <= 0:
            return 1.0

        usage_n = float(pow(current_usage, n))
        threshold_n = float(pow(threshold, n))

        saturation = usage_n / (threshold_n + usage_n)
        return float(1.0 - saturation)

    def compute_affinity(self, stress_level: float) -> float:
        """
        Compute processing affinity based on stress level [0, 1].
        """
        if stress_level <= 0:
            return 1.0

        return self.calculate_dampening(stress_level, 0.4, n=self.hill_n)

    @classmethod
    def regulate_context(cls, requested_tokens: int, current_memory_mb: float, memory_limit_mb: float) -> int:
        """
        Adjust context window size to prevent Memory Famine.
        """
        settings = get_settings()
        dampening = cls.calculate_dampening(current_memory_mb, memory_limit_mb, n=settings.metabolism.hill_n)
        dampened_tokens = int(requested_tokens * dampening)

        if dampening < 0.2:
            logger.warning(
                "memory_famine_imminent",
                usage=current_memory_mb,
                limit=memory_limit_mb,
                dampening=dampening,
            )

        return max(0, dampened_tokens)
