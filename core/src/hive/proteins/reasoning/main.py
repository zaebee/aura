import asyncio
import logging
from typing import Any

import dspy
from aura_core import Observation, SkillProtocol

from config import get_settings

from ._embeddings import generate_embedding as _generate_embedding
from ._engine import AuraNegotiator

logger = logging.getLogger(__name__)

class ReasoningSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Reasoning Protein: Handles LLM interactions, DSPy negotiation, and embeddings.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.negotiator = None

        # Configure DSPy
        if self.settings.llm.model != "rule":
            try:
                dspy.configure(lm=dspy.LM(self.settings.llm.model))
                self.negotiator = self._load_negotiator()
            except Exception as e:
                logger.error(f"Failed to configure DSPy: {e}")

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return ["negotiate", "analyze", "generate_embedding"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "negotiate":
            return await self._negotiate(params)
        elif intent == "generate_embedding":
            return await self._generate_embedding(params.get("text", ""))
        elif intent == "analyze":
             return await self._analyze(params)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    def _load_negotiator(self) -> Any:
        # Simplified loading logic, similar to AuraTransformer._load_negotiator
        from pathlib import Path

        search_paths = [
            Path("/app/core/data/aura_brain.json"),
            Path("/app/data/aura_brain.json"),
            Path("./data/aura_brain.json"),
            Path("/app/core/src/aura_brain.json"),
            Path(__file__).parent.parent.parent.parent / "aura_brain.json",
        ]

        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.insert(0, Path(self.settings.llm.compiled_program_path))

        for path in search_paths:
            try:
                if path.exists() and path.is_file():
                    logger.info(f"Loading compiled DSPy program from {path}")
                    return dspy.load(str(path))
            except Exception:
                continue

        logger.warning("Compiled program not found, using untrained AuraNegotiator")
        return AuraNegotiator()

    async def _negotiate(self, params: dict[str, Any]) -> Observation:
        if not self.negotiator:
             return Observation(success=False, error="Negotiator not initialized")

        bid = params.get("bid")
        context = params.get("context", {})
        history = params.get("history", [])

        try:
            # Wrap synchronous DSPy call in thread
            def call():
                return self.negotiator(
                    input_bid=bid,
                    context=context,
                    history=history
                )

            result = await asyncio.to_thread(call)

            # The result is already a dict from AuraNegotiator.forward
            # containing 'thought' and 'action' (parsed)

            return Observation(success=True, data={
                "action": result["action"]["action"],
                "price": result["action"]["price"],
                "message": result["action"]["message"],
                "thought": result.get("thought", ""),
                "metadata": result.get("metadata", {})
            })
        except Exception as e:
            logger.error(f"Reasoning negotiation failed: {e}")
            return Observation(success=False, error=str(e))

    async def _generate_embedding(self, text: str) -> Observation:
        try:
            embedding = await asyncio.to_thread(_generate_embedding, text)
            return Observation(success=True, data=embedding)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _analyze(self, params: dict[str, Any]) -> Observation:
        # Placeholder for future analysis capabilities
        return Observation(success=True, data={"analysis": "Analyze capability called"})
