from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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
]


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
class PurityReport:
    """The result of an architectural audit."""

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

    async def perceive(self) -> BeeContext: ...


@runtime_checkable
class BeeTransformer(Protocol):
    """T - Transformer: Analyzes purity and generates reports."""

    async def think(self, context: BeeContext) -> PurityReport: ...


@runtime_checkable
class BeeConnector(Protocol):
    """C - Connector: Interacts with GitHub and NATS."""

    async def act(
        self, report: PurityReport, context: BeeContext
    ) -> BeeObservation: ...


@runtime_checkable
class BeeGenerator(Protocol):
    """G - Generator: Updates documentation and chronicles."""

    async def generate(self, report: PurityReport, context: BeeContext) -> None: ...
