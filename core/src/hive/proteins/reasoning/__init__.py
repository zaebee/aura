import asyncio
from typing import Any

import dspy
from aura_core import Observation, SkillProtocol

from config import get_settings
from config.llm import get_raw_key
from hive.transformer.llm.engine import AuraNegotiator


class ReasoningProtein(SkillProtocol[dict[str, Any], Observation]):
    """
    Reasoning Protein: Encapsulates all LLM and DSPy operations.
    Isolates AI logic from nucleotides.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._default_model = None
        self._negotiator = None

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return ["negotiate", "generate_embedding", "analyze"]

    async def initialize(self) -> bool:
        """Initialize DSPy and load compiled programs."""
        try:
            if self.settings.llm.model != "rule":
                dspy.configure(lm=dspy.LM(self.settings.llm.model))
                # In a real scenario, we'd load the compiled program here
                # For now, we'll instantiate the negotiator
                self._negotiator = AuraNegotiator()
            return True
        except Exception:
            return False

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "negotiate":
            return await self._negotiate(params)
        elif intent == "generate_embedding":
            return await self._generate_embedding(params.get("text", ""))
        elif intent == "analyze":
            return await self._analyze(params)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def _negotiate(self, params: dict[str, Any]) -> Observation:
        if not self._negotiator:
            return Observation(success=False, error="Negotiator not initialized")

        try:
            model = params.get("model", self.settings.llm.model)
            temperature = params.get("temperature", self.settings.llm.temperature)

            with dspy.context(lm=dspy.LM(model, temperature=temperature)):
                result = await asyncio.to_thread(
                    self._negotiator,
                    input_bid=params["input_bid"],
                    context=params["context"],
                    history=params.get("history", []),
                )
            return Observation(success=True, data=result)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _generate_embedding(self, text: str) -> Observation:
        if not text:
            return Observation(success=False, error="Text is required")
        try:
            from langchain_mistralai import MistralAIEmbeddings
            embeddings = MistralAIEmbeddings(
                model="mistral-embed",
                mistral_api_key=get_raw_key(self.settings.llm.api_key),
            )
            vector = await asyncio.to_thread(embeddings.embed_query, text)
            return Observation(success=True, data=vector)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _analyze(self, params: dict[str, Any]) -> Observation:
        # Generic analysis capability
        return Observation(success=False, error="Not implemented")
