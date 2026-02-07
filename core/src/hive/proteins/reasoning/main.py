import asyncio
import logging
from typing import Any

import dspy
from aura_core import Observation, SkillProtocol

from config.llm import LLMSettings

from .enzymes.engine import generate_embedding, load_brain

logger = logging.getLogger(__name__)


class ReasoningSkill(
    SkillProtocol[LLMSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Reasoning Protein: Handles LLM logic, DSPy negotiation, and embeddings.
    Standardized following the Crystalline Protein Standard and Enzyme pattern.
    """

    def __init__(self) -> None:
        self.settings: LLMSettings | None = None
        self.provider: dict[str, Any] | None = None
        self.negotiator: Any = None
        self._embed_model: Any = None

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return ["negotiate", "generate_embedding"]

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
        try:
            if intent == "negotiate":
                if not self.negotiator:
                    return Observation(success=False, error="negotiator_not_ready")
                bid = params.get("bid", 0.0)
                context = params.get("context", {})
                history = params.get("history", [])

                def call() -> dict[str, Any]:
                    from typing import cast

                    neg = cast(Any, self.negotiator)
                    return cast(
                        dict[str, Any],
                        neg(
                            input_bid=bid,
                            context=context,
                            history=history,
                        ),
                    )

                from aura_core.gen.aura.dna.v1 import NegotiationResult
                result = await asyncio.to_thread(call)
                res = NegotiationResult(
                    action=result["action"]["action"],
                    price=result["action"]["price"],
                    message=result["action"]["message"],
                    thought=result.get("thought", ""),
                    metadata={str(k): str(v) for k, v in result.get("metadata", {}).items()},
                )
                return Observation(success=True, negotiation_result=res)

            elif intent == "generate_embedding":
                if not self._embed_model:
                    return Observation(success=False, error="embed_model_not_ready")
                text = params.get("text", "")

                emb = await asyncio.to_thread(
                    generate_embedding, text, self._embed_model
                )
                from aura_core.gen.aura.dna.v1 import FloatList
                return Observation(success=True, float_list=FloatList(values=emb))

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            logger.error(f"Reasoning skill error: {e}")
            return Observation(success=False, error=str(e))
