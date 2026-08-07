from typing import Any

from aura_core import SkillProtocol
from aura_core_gen.aura.core.v1 import Observation

from .engine import CoherenceEngine


class CoherenceSkill(SkillProtocol[Any, Any, Any, Any]):
    """Protein wrapper for the UHM Coherence Engine."""

    def __init__(self) -> None:
        self.engine: CoherenceEngine | None = None
        self.settings: Any = None
        self.provider: Any = None

    def get_name(self) -> str:
        return "coherence"

    def get_capabilities(self) -> list[str]:
        return ["vitals", "coherence_check"]

    def bind(self, settings: Any, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        pcrit = 2.0 / 7.0
        if self.settings and hasattr(self.settings, "pcrit"):
            pcrit = float(self.settings.pcrit)
        self.engine = CoherenceEngine(pcrit=pcrit)
        return True

    async def execute(self, intent: str, params: Any) -> Observation:
        if not self.engine:
            return Observation(success=False, error="Coherence engine not initialized")
        return await self.engine.execute(intent, params)

    async def close(self) -> None:
        pass
