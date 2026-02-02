from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from aura_core.dna import (
    ALLOWED_CHAMBERS as ALLOWED_CHAMBERS,
    ALLOWED_ROOT_FILES as ALLOWED_ROOT_FILES,
    MACRO_ATCG_FOLDERS as MACRO_ATCG_FOLDERS,
    find_hive_root as find_hive_root,
)


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
