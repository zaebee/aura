"""
Metabolic Engine - Runtime implementations for the ATCG loop.

This module contains the executable machinery that powers the Hive's metabolism.
The Protocols (the "Law") live in dna.py; this module provides the "Engine".
"""

from typing import Any, cast

import opentelemetry.trace as trace

from .dna import (
    Aggregator,
    Connector,
    Generator,
    Membrane,
    SkillProtocol,
    Transformer,
)
from .types import Observation

tracer = trace.get_tracer(__name__)


class SkillRegistry:
    """Registry for Proteins (Skills) used by the Connector."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillProtocol[Any, Any, Any, Any]] = {}

    def register(self, name: str, skill: SkillProtocol[Any, Any, Any, Any]) -> None:
        self._skills[name] = skill

    def get(self, name: str) -> SkillProtocol[Any, Any, Any, Any] | None:
        return self._skills.get(name)

    async def execute(self, skill_name: str, intent: str, params: Any) -> Observation:
        """Helper to execute a skill by name with tracing."""
        skill = self.get(skill_name)
        if not skill:
            return Observation(success=False, error=f"Skill '{skill_name}' not found")

        with tracer.start_as_current_span(f"skill:{skill_name}") as span:
            span.set_attribute("intent", intent)
            try:
                result = await skill.execute(intent, params)
                obs = cast(Observation, result)
                span.set_attribute("success", obs.success)
                return obs
            except Exception as e:
                span.record_exception(e)
                return Observation(success=False, error=str(e))

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    async def close(self) -> None:
        """Close all registered skills."""
        for skill in self._skills.values():
            if hasattr(skill, "close") and callable(skill.close):
                await skill.close()


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

            # Use registry.execute for tracing and consistency
            last_observation = await self.registry.execute(skill_name, intent, params)

            if not last_observation.success:
                break

        return last_observation

    async def _handle_legacy(self, action: Any, context: Any) -> Observation:
        """Override this for specific connector logic if no steps are provided."""
        return Observation(success=False, error="No steps defined in IntentAction")


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
        with tracer.start_as_current_span("metabolic_loop") as _span:
            # 1. Inbound Membrane
            with tracer.start_as_current_span("nucleotide_membrane_in"):
                if self.membrane and hasattr(self.membrane, "inspect_inbound"):
                    signal = await self.membrane.inspect_inbound(signal)

            # 2. Aggregator (A)
            with tracer.start_as_current_span("nucleotide_aggregator"):
                context = await self.aggregator.perceive(signal, **kwargs)

                # Internal Proprioception: Inject system vitals into context
                try:
                    vitals = await self.aggregator.get_vitals()
                    if hasattr(context, "system_health"):
                        context.system_health = vitals
                    elif isinstance(context, dict) and "system_health" in context:
                        context["system_health"] = vitals
                except Exception as e:
                    # Proprioception should not crash the main loop
                    trace.get_current_span().record_exception(e)

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
