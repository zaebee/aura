from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from .types import Observation

# 1. Define TypeVars for the metabolic steps
S_inv = TypeVar("S_inv", contravariant=True)  # Input Signal
C_cov = TypeVar("C_cov", covariant=True)  # Output Context
C_inv = TypeVar("C_inv", contravariant=True)  # Input Context
I_inv = TypeVar("I_inv", contravariant=True)  # Input Intent
O_cov = TypeVar("O_cov", covariant=True)  # Output Observation
E_cov = TypeVar("E_cov", covariant=True)  # Output Event


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
    "core/scripts": "WorkerDirectives",
    "api-gateway": "HiveGate",
    "core/src/config": "SacredCodex",
    "core/src/hive/services": "LegacyChamber",
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
    "agents/bee-keeper/src/hive/": "KeeperNucleus",
    "adapters": "HiveExtensions",
    "frontend": "HiveWindow",
    "tools": "ToolShed",
    "tests": "OuterValidationPollen",
    "packages": "SharedNucleotides",
    "components": "SpecializedProteins",
    "agents/bee-keeper/src/hive/connector/proteins": "KeeperSecurityCitadel",
}


# 2. Define the Unified Generic Protocols
@runtime_checkable
class Aggregator[S_inv, C_cov](Protocol):
    """Standard sensory organ. Turns Signal into Context."""

    async def perceive(self, signal: S_inv, **kwargs: Any) -> C_cov: ...


@runtime_checkable
class Transformer[C_inv, I_inv](Protocol):
    """Standard reasoning organ. Turns Context into Intent."""

    async def think(self, context: C_inv, **kwargs: Any) -> I_inv: ...


@runtime_checkable
class Connector[I_inv, O_cov, C_inv](Protocol):
    """Standard motor organ. Turns Intent into Observation."""

    async def act(self, action: I_inv, context: C_inv) -> O_cov: ...


@runtime_checkable
class Generator[O_cov, E_cov](Protocol):
    """Standard pulse organ. Turns Observation into Events."""

    async def pulse(self, observation: O_cov) -> list[E_cov]: ...


@runtime_checkable
class Membrane[S_inv, I_inv, C_inv](Protocol):
    """Standard safety organ. Inspects Inbound and Outbound."""

    async def inspect_inbound(self, signal: S_inv) -> S_inv: ...

    async def inspect_outbound(self, decision: I_inv, context: C_inv) -> I_inv: ...


@runtime_checkable
class Skill(Protocol):
    """Protocol for specialized Proteins used by the Connector."""

    def get_name(self) -> str: ...

    def get_capabilities(self) -> list[str]: ...

    async def initialize(self) -> bool: ...

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation: ...


class MetabolicLoop[S_inv, C_cov, I_inv, O_cov, E_cov]:
    """
    Generic ATCG Metabolic Loop.
    Can be used by both core and adapters.
    """

    def __init__(
        self,
        aggregator: Aggregator[S_inv, C_cov],
        transformer: Transformer[C_cov, I_inv],
        connector: Connector[I_inv, O_cov, C_cov],
        generator: Generator[O_cov, E_cov],
        membrane: Membrane[S_inv, I_inv, C_cov] | None = None,
    ):
        self.aggregator = aggregator
        self.transformer = transformer
        self.connector = connector
        self.generator = generator
        self.membrane = membrane

    async def execute(self, signal: S_inv, **kwargs: Any) -> O_cov:
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
        observation = await self.connector.act(decision, context)

        # 6. Generator (G)
        await self.generator.pulse(observation)

        return observation
