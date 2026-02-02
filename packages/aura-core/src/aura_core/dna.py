import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypedDict, runtime_checkable


def find_hive_root() -> Path:
    """Find the repository root by searching upwards for markers."""
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        # Monorepo markers
        if (parent / "core-service").exists() and (parent / "api-gateway").exists():
            return parent
    return Path.cwd()


MACRO_ATCG_FOLDERS = [
    "core-service",
    "api-gateway",
    "frontend",
    "adapters",
    "agents",
    "proto",
    "docs",
    "tools",
    "deploy",
    "packages",
]

ALLOWED_ROOT_FILES = [
    "README.md",
    "llms.txt",
    "HIVE_STATE.md",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
    "Makefile",
    "buf.gen.yaml",
    "buf.yaml",
    ".python-version",
    ".dockerignore",
    ".env.example",
    "compose.yml",
    ".pre-commit-config.yaml",
    "CLAUDE.md",
    "CRYPTO_INTEGRATION_SUMMARY.md",
    "CRYPTO_QUICKSTART.md",
]

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
    "packages": "SharedNucleotides",
}


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
    message_id: int | None = None
    error: str | None = None
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """An event emitted to the Hive's blood stream (NATS)."""

    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class SearchResult(TypedDict):
    item_id: str
    name: str
    base_price: float
    description_snippet: str | None


class NegotiationResult(TypedDict, total=False):
    accepted: dict[str, Any] | None
    countered: dict[str, Any] | None
    rejected: dict[str, Any] | None
    ui_required: dict[str, Any] | None
    error: str | None


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
