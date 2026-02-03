"""Core-service ATCG Protocol definitions.

Imports base types from aura_core and defines specialized protocols
for the core negotiation service with stricter type hints.
"""

from typing import Any, Protocol, runtime_checkable

from aura_core import (
    Event,
    HiveContext,
    IntentAction,
    Observation,
)

# Re-export for backward compatibility
__all__ = [
    "Event",
    "HiveContext",
    "IntentAction",
    "Observation",
    "Aggregator",
    "Transformer",
    "Connector",
    "Generator",
    "Membrane",
]


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Consolidates internal state and external metrics."""

    async def perceive(self, signal: Any) -> HiveContext: ...

    async def get_system_metrics(self) -> dict[str, Any]: ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Handles the DSPy reasoning."""

    async def think(self, context: HiveContext) -> IntentAction: ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Manages gRPC and External API outputs."""

    async def act(self, action: IntentAction, context: HiveContext) -> Observation: ...


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
        self, decision: IntentAction, context: HiveContext
    ) -> IntentAction:
        """Verify and enforce economic rules on outbound decisions."""
        ...
