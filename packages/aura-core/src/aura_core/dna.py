from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import opentelemetry.trace as trace

from .types import Observation

tracer = trace.get_tracer(__name__)

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
class Skill(Protocol):
    """Protocol for specialized Proteins used by the Connector."""

    def get_name(self) -> str: ...

    def get_capabilities(self) -> list[str]: ...

    async def initialize(self) -> bool: ...

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation: ...


class SkillRegistry:
    """Registry for Proteins (Skills) used by the Connector."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, name: str, skill: Skill) -> None:
        self._skills[name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


@runtime_checkable
class Connector[I_inv, O_cov, C_inv](Protocol):
    """Standard motor organ. Turns Intent into Observation."""

    registry: SkillRegistry

    async def act(self, action: I_inv, context: C_inv) -> O_cov: ...


class BaseConnector(Connector[Any, Observation, Any]):
    """
    Composite Connector implementation.
    Handles sequential skill execution defined in IntentAction steps.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def act(self, action: Any, context: Any) -> Observation:
        # 1. Check if we have steps
        steps = getattr(action, "steps", [])
        if not steps:
            # Fallback for single action or legacy support
            return await self._handle_legacy(action, context)

        last_observation = Observation(success=True)

        for i, step in enumerate(steps):
            skill_name = step.get("skill")
            intent = step.get("intent")
            params = step.get("params", {}).copy()

            # Pass context and previous results to the next step
            params["_context"] = context
            if i > 0:
                params["_previous_observation"] = last_observation

            skill = self.registry.get(skill_name)
            if not skill:
                return Observation(
                    success=False, error=f"Skill '{skill_name}' not found in registry"
                )

            # Trace individual skill execution
            with tracer.start_as_current_span(f"skill:{skill_name}") as span:
                span.set_attribute("intent", intent)
                span.set_attribute("step_index", i)

                try:
                    last_observation = await skill.execute(intent, params)
                    span.set_attribute("success", last_observation.success)
                except Exception as e:
                    span.record_exception(e)
                    return Observation(success=False, error=str(e))

            if not last_observation.success:
                break

        return last_observation

    async def _handle_legacy(self, action: Any, context: Any) -> Observation:
        """Override this for specific connector logic if no steps are provided."""
        return Observation(success=False, error="No steps defined in IntentAction")


@runtime_checkable
class Generator[O_cov, E_cov](Protocol):
    """Standard pulse organ. Turns Observation into Events."""

    async def pulse(self, observation: O_cov) -> list[E_cov]: ...


@runtime_checkable
class Membrane[S_inv, I_inv, C_inv](Protocol):
    """Standard safety organ. Inspects Inbound and Outbound."""

    async def inspect_inbound(self, signal: S_inv) -> S_inv: ...

    async def inspect_outbound(self, decision: I_inv, context: C_inv) -> I_inv: ...


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
        with tracer.start_as_current_span("metabolic_loop") as span:
            # 1. Inbound Membrane
            with tracer.start_as_current_span("nucleotide_membrane_in"):
                if self.membrane and hasattr(self.membrane, "inspect_inbound"):
                    signal = await self.membrane.inspect_inbound(signal)

            # 2. Aggregator (A)
            with tracer.start_as_current_span("nucleotide_aggregator"):
                context = await self.aggregator.perceive(signal, **kwargs)

            # 3. Transformer (T)
            # Note: Some transformers might need extra data passed in via kwargs
            with tracer.start_as_current_span("nucleotide_transformer"):
                decision = await self.transformer.think(context, **kwargs)

            # 4. Outbound Membrane
            with tracer.start_as_current_span("nucleotide_membrane_out"):
                if self.membrane and hasattr(self.membrane, "inspect_outbound"):
                    decision = await self.membrane.inspect_outbound(decision, context)

            # 5. Connector (C)
            with tracer.start_as_current_span("nucleotide_connector"):
                observation = await self.connector.act(decision, context)

            # 6. Generator (G)
            with tracer.start_as_current_span("nucleotide_generator"):
                await self.generator.pulse(observation)

            return observation
