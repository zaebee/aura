from typing import Any

import structlog
from aura_core import Observation, SkillProtocol

from config.perception import PerceptionSettings

from .engine import PerceptionEngine
from .schema import PerceiveImageParams, PerceiveImageResult

logger = structlog.get_logger(__name__)


class PerceptionSkill(
    SkillProtocol[PerceptionSettings, PerceptionEngine, dict[str, Any], Observation]
):
    """
    Perception Protein: Handles multimodal image perception using Ollama.
    """

    def __init__(self) -> None:
        self.settings: PerceptionSettings | None = None
        self.provider: PerceptionEngine | None = None
        self._capabilities = {
            "perceive_image": self._perceive_image,
        }

    def get_name(self) -> str:
        return "perception"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: PerceptionSettings, provider: PerceptionEngine) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return self.settings is not None and self.provider is not None

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Perception skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _perceive_image(self, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_ready")

        p = PerceiveImageParams(**params)
        item = await self.provider.perceive_image(p.image_bytes)

        return Observation(success=True, data=PerceiveImageResult(item=item).model_dump())
