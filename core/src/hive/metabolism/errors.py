"""
Metabolic Errors: Custom exceptions for the Hive's ATCG loop.
"""


class MetabolicError(Exception):
    """Base class for all metabolic errors."""

    pass


class MetabolicSecurityError(MetabolicError):
    """Raised when a security guardrail or membrane enforcement fails."""

    pass


class GeometricCeilingError(MetabolicError):
    """Raised when self-modeling recursion depth exceeds physical limits (SADmax=3)."""

    pass


class ApoptosisTrigger(MetabolicError):
    """Signal for emergency shutdown due to critical loss of coherence."""

    pass


class DeathSpiralError(ApoptosisTrigger):
    """Raised when purity falls below the critical threshold (2/7)."""

    pass
