from dataclasses import dataclass, field
from typing import Any


@dataclass
class NegotiationOffer:
    """Internal representation of an incoming bid."""

    bid_amount: float
    reputation: float
    agent_did: str


@dataclass
class HiveContext:
    """Consolidated context for the Hive's decision making."""

    item_id: str
    offer: NegotiationOffer
    item_data: dict[str, Any] = field(default_factory=dict)
    system_health: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentAction:
    """Strictly typed intent returned by the Transformer."""

    action: str  # "accept", "counter", "reject", "ui_required"
    price: float
    message: str
    thought: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureIntent(IntentAction):
    """Specialized intent for when the LLM or processing fails."""

    error: str = ""
    action: str = "error"
    price: float = 0.0
    message: str = "Internal processing error. Defaulting to safe state."


@dataclass
class Observation:
    """Observation resulting from an action."""

    success: bool
    data: Any
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""

    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=lambda: 0.0)
