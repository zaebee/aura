import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypedDict, runtime_checkable


def find_hive_root() -> Path:
    """Find the repository root by searching upwards for markers."""
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        # Monorepo markers
        if (parent / "core").exists() and (parent / "api-gateway").exists():
            return parent
    return Path.cwd()


MACRO_ATCG_FOLDERS = [
    "core",
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
    "core/migrations": "HiveEvolutionaryScrolls",
    "core/tests": "ValidationPollen",
    "api-gateway": "HiveGate",
    "core/src/config": "SacredCodex",
    "core/src/hive/services": "WorkerDirectives",
    "core/src/hive/transformer": "ReasoningNucleus",
    "core/src/hive/connector/proteins": "SecurityCitadel",
    "core/src/hive/membrane": "HiveMembrane",
    "core/src/hive/aggregator": "SensoryNexus",
    "core/src/hive/generator": "NeuralPulse",
    "core/src/hive/metabolism": "SacredCodex",
    "deploy": "HiveArmor",
    "proto": "SacredScrolls",
    "docs": "ChroniclersArchive",
    "agents": "WorkerCells",
    "adapters": "HiveExtensions",
    "frontend": "HiveWindow",
    "tools": "ToolShed",
    "tests": "OuterValidationPollen",
    "packages": "SharedNucleotides",
    "components": "SpecializedProteins",
    "agents/bee-keeper/src/hive/connector/proteins": "KeeperSecurityCitadel",
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
class SkillProtocol(Protocol):
    """Protocol for specialized Hive Organs (Proteins)."""

    def get_name(self) -> str: ...

    def get_capabilities(self) -> list[str]: ...

    async def initialize(self) -> bool: ...

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation: ...


@runtime_checkable
class BeeDNA(Protocol):
    """Protocol for the Hive components."""

    pass


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Consolidates internal state and external metrics."""

    async def perceive(self, signal: Any) -> HiveContext: ...

    async def get_system_metrics(self) -> dict[str, Any]: ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Decides on actions (Handles reasoning)."""

    async def think(self, context: HiveContext) -> IntentAction: ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Executes actions (Manages gRPC and External API outputs)."""

    async def act(self, action: IntentAction, context: HiveContext) -> Observation: ...


@runtime_checkable
class Generator(Protocol):
    """G - Generator: Emits events (NATS heartbeats and events)."""

    async def pulse(self, observation: Observation) -> list[Event]: ...


@runtime_checkable
class Membrane(Protocol):
    """M - Membrane: Inbound/Outbound safety checks (Guardrails)."""

    async def inspect_inbound(self, signal: Any) -> Any:
        """Sanitize and validate inbound signals."""
        ...

    async def inspect_outbound(
        self, decision: IntentAction, context: HiveContext
    ) -> IntentAction:
        """Verify and enforce economic rules on outbound decisions."""
        ...


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


@dataclass
class TelegramContext:
    """Context specific to Telegram interactions."""

    user_id: int
    chat_id: int
    hive_context: HiveContext | None = None
    message_text: str | None = None
    callback_data: str | None = None
    fsm_state: str | None = None
    fsm_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIAction:
    """Structured action for the Telegram UI."""

    text: str
    reply_markup: Any | None = None
    parse_mode: str | None = "Markdown"
    action_type: str = (
        "send_message"  # e.g., "send_message", "answer_callback", "edit_message"
    )
    show_thinking: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


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
        core_response: NegotiationResult | None = None,
        search_results: list[SearchResult] | None = None,
    ) -> UIAction: ...


@runtime_checkable
class TelegramConnector(Protocol):
    """C - Connector: Executes UI actions and gRPC calls."""

    async def act(self, action: UIAction, context: TelegramContext) -> Observation: ...

    async def call_core(self, context: TelegramContext) -> NegotiationResult: ...

    async def search_core(self, query: str) -> list[SearchResult]: ...


@runtime_checkable
class TelegramGenerator(Protocol):
    """G - Generator: Emits events to NATS."""

    async def pulse(self, observation: Observation) -> list[Event]: ...


class MetabolicLoop:
    """
    Generic ATCG Metabolic Loop.
    Can be used by both core and adapters.
    """

    def __init__(
        self,
        aggregator: Any,
        transformer: Any,
        connector: Any,
        generator: Any,
        membrane: Any = None,
    ):
        self.aggregator = aggregator
        self.transformer = transformer
        self.connector = connector
        self.generator = generator
        self.membrane = membrane

    async def execute(self, signal: Any, **kwargs: Any) -> Observation:
        """
        Execute one full metabolic cycle:
        Signal -> [Membrane In] -> Aggregator -> Transformer -> [Membrane Out] -> Connector -> Generator
        """
        # 1. Inbound Membrane
        if self.membrane and hasattr(self.membrane, "inspect_inbound"):
            signal = await self.membrane.inspect_inbound(signal)

        # 2. Aggregator (A)
        context = await self.aggregator.perceive(signal, **kwargs)

        # 3. Transformer (T)
        # Note: Some transformers might need extra data passed in via kwargs
        decision = await self.transformer.think(context, **kwargs)

        # 4. Outbound Membrane
        if self.membrane and hasattr(self.membrane, "inspect_outbound"):
            decision = await self.membrane.inspect_outbound(decision, context)

        # 5. Connector (C)
        observation: Observation = await self.connector.act(decision, context)

        # 6. Generator (G)
        await self.generator.pulse(observation)

        return observation
