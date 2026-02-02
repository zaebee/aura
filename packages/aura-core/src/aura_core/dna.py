from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class NegotiationOffer:
    """Internal representation of an incoming bid."""

    bid_amount: float
    reputation: float = 1.0
    agent_did: str = "unknown"


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
class Observation:
    """Observation resulting from an action."""

    success: bool
    data: Any = None
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""

    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=lambda: 0.0)


@runtime_checkable
class BeeDNA(Protocol):
    """Protocol for the Hive components."""

    pass


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Extracts signals into context."""

    async def perceive(self, signal: Any, state_data: dict[str, Any]) -> Any: ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Decides on actions."""

    async def think(self, context: Any) -> Any: ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Executes actions."""

    async def act(self, action: Any, context: Any) -> Observation: ...


@runtime_checkable
class Generator(Protocol):
    """G - Generator: Emits events."""

    async def pulse(self, observation: Observation) -> list[Event]: ...
