from dataclasses import dataclass

from aura_core.dna import (
    Event,
    HiveContext,
    IntentAction,
    NegotiationOffer,
    Observation,
)


@dataclass
class FailureIntent(IntentAction):
    """Specialized intent for when the LLM or processing fails."""

    error: str = ""
    action: str = "error"
    price: float = 0.0
    message: str = "Internal processing error. Defaulting to safe state."


# Exporting these for backward compatibility within core-service
__all__ = [
    "NegotiationOffer",
    "HiveContext",
    "IntentAction",
    "FailureIntent",
    "Observation",
    "Event",
]
