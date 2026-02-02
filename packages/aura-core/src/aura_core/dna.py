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
    "core-service/src/hive/metabolism/config": "SacredCodex",
    "core-service/src/services": "WorkerDirectives",
    "core-service/src/hive/transformer": "ReasoningNucleus",
    "core-service/src/hive/connector": "SecurityCitadel",
    "core-service/src/hive/transformer/prompts": "EchoChamber",
    "core-service/src/hive/guard": "HiveMembrane",
    "deploy": "HiveArmor",
    "proto": "SacredScrolls",
    "docs": "ChroniclersArchive",
    "agents": "WorkerCells",
    "adapters": "HiveExtensions",
    "frontend": "HiveWindow",
    "tools": "ToolShed",
    "tests": "OuterValidationPollen",
    "packages": "DNACentralArchive",
}

# HIVE DNA: CONFIGURATION PROTOCOLS
# 1. Cross-namespace service discovery MUST use full FQDN paths (e.g., service.namespace.svc.cluster.local).
# 2. Monitoring (Technical Layer) and Aura Core (Business Layer) integration must be deterministic and traceable.


@runtime_checkable
class Aggregator(Protocol):
    """A - Aggregator: Consolidates internal state and external metrics."""

    async def perceive(self, signal: Any) -> Any: ...

    async def get_system_metrics(self) -> dict[str, Any]: ...


@runtime_checkable
class Transformer(Protocol):
    """T - Transformer: Handles the DSPy reasoning."""

    async def think(self, context: Any) -> Any: ...


@runtime_checkable
class Connector(Protocol):
    """C - Connector: Manages gRPC and External API outputs."""

    async def act(self, action: Any, context: Any) -> Any: ...


@runtime_checkable
class Generator(Protocol):
    """G - Generator: Emits NATS heartbeats and events."""

    async def pulse(self, observation: Any) -> list[Any]: ...


@runtime_checkable
class Membrane(Protocol):
    """Inbound/Outbound safety checks (Guardrails)."""

    async def inspect_inbound(self, signal: Any) -> Any:
        """Sanitize and validate inbound signals."""
        ...

    async def inspect_outbound(self, decision: Any, context: Any) -> Any:
        """Verify and enforce economic rules on outbound decisions."""
        ...


# BeeKeeper Specific Protocols
@runtime_checkable
class BeeAggregator(Protocol):
    """A - Aggregator: Gathers signals from Git, Prometheus, and Filesystem."""

    async def sense(self, event_name: str = "manual") -> Any: ...
    async def test_brain_connectivity(self) -> bool: ...


@runtime_checkable
class BeeTransformer(Protocol):
    """T - Transformer: Analyzes purity and generates audit observations."""

    async def reflect(self, context: Any) -> Any: ...


@runtime_checkable
class BeeConnector(Protocol):
    """C - Connector: Interacts with GitHub and NATS."""

    async def interact(self, report: Any, context: Any) -> Any: ...


@runtime_checkable
class BeeGenerator(Protocol):
    """G - Generator: Updates documentation and chronicles."""

    async def generate(
        self,
        report: Any,
        context: Any,
        observation: Any,
    ) -> None: ...
