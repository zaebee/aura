from typing import Any, Protocol, runtime_checkable

from .types import (
    AuditObservation,
    BeeContext,
    BeeObservation,
    Event,
    HiveContext,
    IntentAction,
    NegotiationOffer,
    Observation,
    TelegramContext,
    UIAction,
)


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


# BeeKeeper Protocols
@runtime_checkable
class BeeAggregator(Protocol):
    """A - Aggregator: Gathers signals from Git, Prometheus, and Filesystem."""
    async def perceive(self) -> BeeContext: ...
    async def test_brain_connectivity(self) -> bool: ...


@runtime_checkable
class BeeTransformer(Protocol):
    """T - Transformer: Analyzes purity and generates reports."""
    async def think(self, context: BeeContext) -> AuditObservation: ...


@runtime_checkable
class BeeConnector(Protocol):
    """C - Connector: Interacts with GitHub and NATS."""
    async def act(self, report: AuditObservation, context: BeeContext) -> BeeObservation: ...


@runtime_checkable
class BeeGenerator(Protocol):
    """G - Generator: Updates documentation and chronicles."""
    async def generate(self, report: AuditObservation, context: BeeContext, observation: BeeObservation) -> None: ...


# Telegram Bot Protocols
@runtime_checkable
class BeeDNA(Protocol):
    """Protocol for the Telegram Bot Hive components."""

    pass


@runtime_checkable
class TelegramAggregator(Protocol):
    """A - Aggregator: Extracts Telegram signals into context."""

    async def perceive(
        self, signal: Any, state_data: dict[str, Any]
    ) -> TelegramContext: ...


@runtime_checkable
class TelegramTransformer(Protocol):
    """T - Transformer: Decides on UI actions."""

    async def think(
        self,
        context: TelegramContext,
        core_response: Any | None = None,  # NegotiationResult
        search_results: list[Any] | None = None,  # list[SearchResult]
    ) -> UIAction: ...


@runtime_checkable
class TelegramConnector(Protocol):
    """C - Connector: Executes UI actions and gRPC calls."""

    async def act(self, action: UIAction, context: TelegramContext) -> Observation: ...

    async def call_core(self, context: TelegramContext) -> Any: ...  # NegotiationResult

    async def search_core(self, query: str) -> list[Any]: ...  # list[SearchResult]


@runtime_checkable
class TelegramGenerator(Protocol):
    """G - Generator: Emits events to NATS."""

    async def pulse(self, observation: Observation) -> list[Event]: ...


# Sacred Roles for Infrastructure
ALLOWED_CHAMBERS = {
    "core-service/migrations": "HiveEvolutionaryScrolls",
    "core-service/tests": "ValidationPollen",
    "api-gateway": "HiveGate",
    "core-service/src/config": "SacredCodex",
    "core-service/src/services": "WorkerDirectives",
    "core-service/src/llm": "ReasoningNucleus",
    "core-service/src/crypto": "SecurityCitadel",
    "core-service/src/prompts": "EchoChamber",
    "core-service/src/guard": "HiveMembrane",
    "deploy": "HiveArmor",
    "proto": "SacredScrolls",
    "docs": "ChroniclersArchive",
    "agents": "WorkerCells",
    "adapters": "HiveExtensions",
    "frontend": "HiveWindow",
    "tools": "ToolShed",
    "tests": "OuterValidationPollen",
    "packages": "HiveNucleotides",
}
