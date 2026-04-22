"""
Hill Regulator: Cooperative Kinetics for Resource Homeostasis.

Uses the Hill Equation (n=2.8) to prevent Memory Famine (OOM)
by dampening processing loads as they approach physical or logical limits.
"""

import structlog

logger = structlog.get_logger(__name__)


class HillRegulator:
    """
    Bio-digital resource regulator based on the Hill Equation.

    Formula:
        saturation = usage^n / (threshold^n + usage^n)
        dampening = 1.0 - saturation

    Attributes:
        HILL_N (float): Hill coefficient, set to 2.8 for Quantum Regeneration.
    """

    HILL_N: float = 2.8

    @classmethod
    def calculate_dampening(cls, current_usage: float, threshold: float) -> float:
        """
        Calculate dampening factor [0, 1].

        Args:
            current_usage: Current resource consumption (e.g., memory in MB).
            threshold: The point where saturation is 0.5 (half-maximal effect).

        Returns:
            A multiplier for dampening activity. 1.0 means no dampening, 0.0 means full stop.
        """
        if threshold <= 0:
            return 0.0
        if current_usage <= 0:
            return 1.0

        n = cls.HILL_N
        usage_n = pow(current_usage, n)
        threshold_n = pow(threshold, n)

        saturation = usage_n / (threshold_n + usage_n)
        return 1.0 - saturation

    @classmethod
    def regulate_context(
        cls, requested_tokens: int, current_memory_mb: float, memory_limit_mb: float
    ) -> int:
        """
        Adjust context window size to prevent Memory Famine.

        Args:
            requested_tokens: Target number of tokens for LLM.
            current_memory_mb: Current RSS or memory usage.
            memory_limit_mb: The threshold where we must aggressively dampen.

        Returns:
            Dampened token count.
        """
        dampening = cls.calculate_dampening(current_memory_mb, memory_limit_mb)
        dampened_tokens = int(requested_tokens * dampening)

        if dampening < 0.2:
            logger.warning(
                "memory_famine_imminent",
                usage=current_memory_mb,
                limit=memory_limit_mb,
                dampening=dampening,
            )

        return max(0, dampened_tokens)
