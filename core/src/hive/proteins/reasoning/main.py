import asyncio
import logging
from typing import Any

import dspy
from aura_core import Observation, SkillProtocol

from config.llm import LLMSettings

from ._internal import generate_embedding, load_brain
from .schema import EmbeddingParams, NegotiationParams, NegotiationResult

logger = logging.getLogger(__name__)


class ReasoningSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Reasoning Protein: Handles LLM logic, DSPy negotiation, and embeddings.
    Standardized following the Crystalline Protein Standard.
    """

    def __init__(self) -> None:
        self.settings: LLMSettings | None = None
        self.negotiator = None

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return ["negotiate", "generate_embedding"]

    async def initialize(self, settings: LLMSettings | None = None) -> bool:
        self.settings = settings
        if self.settings and self.settings.model != "rule":
            try:
                dspy.configure(lm=dspy.LM(self.settings.model))
                self.negotiator = load_brain(
                    getattr(self.settings, "compiled_program_path", None)
                )
            except Exception as e:
                logger.error(f"Failed to configure DSPy: {e}")
                return False
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        try:
            if intent == "negotiate":
                if not self.negotiator:
                    return Observation(success=False, error="negotiator_not_ready")
                p_neg = NegotiationParams(**params)

                def call() -> dict[str, Any]:
                    from typing import cast
                    neg = cast(Any, self.negotiator)
                    return cast(dict[str, Any], neg(
                        input_bid=p_neg.bid,
                        context=p_neg.context,
                        history=p_neg.history,
                    ))

                result = await asyncio.to_thread(call)
                data = {
                    "action": result["action"]["action"],
                    "price": result["action"]["price"],
                    "message": result["action"]["message"],
                    "thought": result.get("thought", ""),
                    "metadata": result.get("metadata", {}),
                }
                return Observation(
                    success=True, data=NegotiationResult(**data).model_dump()
                )

            elif intent == "generate_embedding":
                p_emb = EmbeddingParams(**params)
                emb = await asyncio.to_thread(generate_embedding, p_emb.text)
                return Observation(success=True, data=emb)

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            logger.error(f"Reasoning skill error: {e}")
            return Observation(success=False, error=str(e))
