from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class BeeContext:
    """Consolidated context for the BeeKeeper's audit."""
    git_diff: str
    hive_metrics: dict[str, Any]
    filesystem_map: list[str]
    repo_name: str
    event_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PurityReport:
    """The result of an architectural audit."""
    is_pure: bool
    heresies: list[str] = field(default_factory=list)
    narrative: str = ""
    reasoning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeeObservation:
    """Observation resulting from BeeKeeper's actions."""
    success: bool
    github_comment_url: str = ""
    nats_event_sent: bool = False
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
    async def act(self, report: PurityReport, context: BeeContext) -> BeeObservation: ...


@runtime_checkable
class BeeGenerator(Protocol):
    """G - Generator: Updates documentation and chronicles."""
    async def generate(self, report: PurityReport, context: BeeContext) -> None: ...
