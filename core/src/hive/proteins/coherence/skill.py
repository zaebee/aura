from typing import Any

from aura_core import SkillProtocol
from aura_core_gen.aura.core.v1 import Observation

from .engine import CoherenceEngine


class CoherenceSkill(SkillProtocol[Any, Any, Any, Any]):
    """Protein wrapper for the UHM Coherence Engine."""

    def __init__(self) -> None:
        self.engine = CoherenceEngine()
        self.settings = None
        self.provider = None

    def get_name(self) -> str:
        return "coherence"

    def get_capabilities(self) -> list[str]:
        return ["vitals", "coherence_check"]

    def bind(self, settings: Any, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: Any) -> Observation:
        return await self.engine.execute(intent, params)

    async def close(self) -> None:
        pass
