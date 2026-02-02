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
    "core-service/scripts": "HiveAutomationScrolls",
    "core-service/data": "HiveMemory",
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
    # ATCG Sub-structures (legal within hive/ directories)
    "proteins": "EnzymaticHelpers",
    "metabolism": "MetabolicCore",
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


# --- bee.Keeper Protocols ---


@dataclass
class BeeContext:
    """Consolidated context for the BeeKeeper's audit."""

    git_diff: str
    hive_metrics: dict[str, Any]
    filesystem_map: list[str]
    repo_name: str
    event_name: str = "manual"
    event_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditObservation:
    """The raw result of an architectural audit."""

    is_pure: bool
    heresies: list[str] = field(default_factory=list)
    narrative: str = ""
    reasoning: str = ""
    execution_time: float = 0.0
    token_usage: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeeObservation:
    """Observation resulting from BeeKeeper's actions."""

    success: bool
    github_comment_url: str = ""
    nats_event_sent: bool = False
    injuries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BeeAggregator(Protocol):
    """A - Aggregator: Gathers signals from Git, Prometheus, and Filesystem."""

    async def sense(self, event_name: str = "manual") -> BeeContext: ...
    async def test_brain_connectivity(self) -> bool: ...


@runtime_checkable
class BeeTransformer(Protocol):
    """T - Transformer: Analyzes purity and generates audit observations."""

    async def reflect(self, context: BeeContext) -> AuditObservation: ...


@runtime_checkable
class BeeConnector(Protocol):
    """C - Connector: Interacts with GitHub and NATS."""

    async def interact(
        self, report: AuditObservation, context: BeeContext
    ) -> BeeObservation: ...


@runtime_checkable
class BeeGenerator(Protocol):
    """G - Generator: Updates documentation and chronicles."""

    async def generate(
        self,
        report: AuditObservation,
        context: BeeContext,
        observation: BeeObservation,
    ) -> None: ...
