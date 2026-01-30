from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class HiveContext:
    """Consolidated context for the Hive's decision making."""

    item_id: str
    bid_amount: float
    agent_did: str
    reputation: float
    item_data: dict[str, Any] = field(default_factory=dict)
    system_health: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """Decision made by the Transformer."""

    action: str  # "accept", "counter", "reject"
    price: float
    message: str
    reasoning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


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


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Consolidates internal state and external metrics."""

    async def perceive(self, signal: Any) -> HiveContext: ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Handles the DSPy reasoning."""

    async def think(self, context: HiveContext) -> Decision: ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Manages gRPC and External API outputs."""

    async def act(self, action: Decision, context: HiveContext) -> Observation: ...


@runtime_checkable
class Generator(Protocol):
    """G - Generator: Emits NATS heartbeats and events."""

    async def pulse(self, observation: Observation) -> list[Event]: ...


@runtime_checkable
class Membrane(Protocol):
    """Inbound/Outbound safety checks (Guardrails)."""

    async def inspect_inbound(self, signal: Any) -> Any:
        """Sanitize and validate inbound signals."""
        ...

    async def inspect_outbound(
        self, decision: Decision, context: HiveContext
    ) -> Decision:
        """Verify and enforce economic rules on outbound decisions."""
        ...
