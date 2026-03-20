"""
Metabolic Errors: Custom exceptions for the Hive's ATCG loop.
"""


class MetabolicError(Exception):
    """Base class for all metabolic errors."""

    pass


class MetabolicSecurityError(MetabolicError):
    """Raised when a security guardrail or membrane enforcement fails."""

    pass
