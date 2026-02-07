import asyncio
import logging
from typing import Any

import dspy
from aura_core import Observation, SkillProtocol

from config.llm import LLMSettings

from .engine import generate_embedding, load_brain
from .schema import EmbeddingParams, NegotiationParams, NegotiationResult

logger = logging.getLogger(__name__)


class ReasoningSkill(
    SkillProtocol[LLMSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Reasoning Protein: Handles LLM logic, DSPy negotiation, and embeddings.
    """

    def __init__(self) -> None:
        self.settings: LLMSettings | None = None
        self.provider: dict[str, Any] | None = None
        self.negotiator: Any = None
        self._embed_model: Any = None
        self._capabilities = {
            "negotiate": self._negotiate,
            "generate_embedding": self._generate_embedding,
        }

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: LLMSettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        if not self.settings or not self.provider:
            return False

        if "rule" not in self.settings.model.lower():
            try:
                lm = self.provider.get("lm")
                if lm:
                    dspy.configure(lm=lm)

                self.negotiator = load_brain(
                    getattr(self.settings, "compiled_program_path", None)
                )
                self._embed_model = self.provider.get("embedder")
            except Exception as e:
                logger.error(f"Failed to initialize Reasoning: {e}")
                return False
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Reasoning skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _negotiate(self, params: dict[str, Any]) -> Observation:
        if not self.negotiator:
            return Observation(success=False, error="negotiator_not_ready")
        p_neg = NegotiationParams(**params)

        def call() -> dict[str, Any]:
            from typing import cast

            neg = cast(Any, self.negotiator)
            return cast(
                dict[str, Any],
                neg(
                    input_bid=p_neg.bid,
                    context=p_neg.context,
                    history=p_neg.history,
                ),
            )

        result = await asyncio.to_thread(call)
        data = {
            "action": result["action"]["action"],
            "price": result["action"]["price"],
            "message": result["action"]["message"],
            "thought": result.get("thought", ""),
            "metadata": result.get("metadata", {}),
        }
        return Observation(success=True, data=NegotiationResult(**data).model_dump())

    async def _generate_embedding(self, params: dict[str, Any]) -> Observation:
        if not self._embed_model:
            return Observation(success=False, error="embed_model_not_ready")
        p_emb = EmbeddingParams(**params)

        emb = await asyncio.to_thread(generate_embedding, p_emb.text, self._embed_model)
        return Observation(success=True, data=emb)
