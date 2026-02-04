from typing import Any

from aura_core import Observation, SkillProtocol, SystemVitals
from config import get_settings
from hive.aggregator.vitals import MetricsCache, fetch_vitals


class TelemetryProtein(SkillProtocol[dict[str, Any], Observation]):
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
        if intent == "get_vitals":
            vitals = await fetch_vitals(self._metrics_cache, self.settings)
            return Observation(success=True, data=vitals)
        elif intent == "fetch_metrics":
            # Placeholder for raw metrics fetch
            return Observation(success=True, data={})

        return Observation(success=False, error=f"Unknown intent: {intent}")
