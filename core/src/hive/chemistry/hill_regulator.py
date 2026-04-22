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
    """

    HILL_N: float = 2.8

    def __init__(self, coefficient: float = 2.8):
        self.HILL_N = coefficient

    @classmethod
    def calculate_dampening(cls, current_usage: float, threshold: float) -> float:
        """
        Calculate dampening factor [0, 1].
        """
        if threshold <= 0:
            return 0.0
        if current_usage <= 0:
            return 1.0

        # Use class HILL_N if called as classmethod, but instance might have its own
        # For simplicity in this implementation, we allow both.
        # But here we just use 2.8 as default if not instantiated.
        n = 2.8

        usage_n = float(pow(current_usage, n))
        threshold_n = float(pow(threshold, n))

        saturation = usage_n / (threshold_n + usage_n)
        return float(1.0 - saturation)

    def compute_affinity(self, stress_level: float) -> float:
        """
        Compute processing affinity based on stress level [0, 1].
        We use a strict threshold of 0.4 to allow affinity to drop below 0.1.
        """
        if stress_level <= 0:
            return 1.0

        n = self.HILL_N
        usage_n = float(pow(stress_level, n))
        threshold_n = float(pow(0.4, n)) # K = 0.4

        saturation = usage_n / (threshold_n + usage_n)
        return float(1.0 - saturation)

    @classmethod
    def regulate_context(cls, requested_tokens: int, current_memory_mb: float, memory_limit_mb: float) -> int:
        """
        Adjust context window size to prevent Memory Famine.
        """
        dampening = cls.calculate_dampening(current_memory_mb, memory_limit_mb)
        dampened_tokens = int(requested_tokens * dampening)

        if dampening < 0.2:
            logger.warning("memory_famine_imminent",
                           usage=current_memory_mb,
                           limit=memory_limit_mb,
                           dampening=dampening)

        return max(0, dampened_tokens)
