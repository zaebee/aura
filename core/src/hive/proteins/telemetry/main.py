from typing import Any

from aura_core import Observation, SkillProtocol, SystemVitals
from config import get_settings
from ._vitals import MetricsCache, fetch_vitals


class TelemetrySkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Telemetry Protein: Encapsulates Prometheus metrics and system vitals.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def get_name(self) -> str:
        return "telemetry"

    def get_capabilities(self) -> list[str]:
        return ["get_vitals", "fetch_metrics"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        match intent:
            case "get_vitals":
                vitals = await fetch_vitals(self._metrics_cache, self.settings)
                return Observation(success=True, data=vitals)
            case "fetch_metrics":
                return Observation(success=True, data={})

        return Observation(success=False, error=f"Unknown intent: {intent}")
