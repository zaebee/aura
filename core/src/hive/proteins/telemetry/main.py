import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config import get_settings

from ._metrics import negotiation_accepted_total, negotiation_total
from ._vitals import MetricsCache, fetch_vitals

logger = logging.getLogger(__name__)

class TelemetrySkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Telemetry Protein: Handles system metrics and health checks.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def get_name(self) -> str:
        return "telemetry"

    def get_capabilities(self) -> list[str]:
        return ["fetch_metrics", "health_check", "increment_counter"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "fetch_metrics" or intent == "get_vitals":
            return await self._fetch_metrics()
        elif intent == "health_check":
            return Observation(success=True, data={"status": "healthy"})
        elif intent == "increment_counter":
            return await self._increment_counter(params)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def _fetch_metrics(self) -> Observation:
        try:
            vitals = await fetch_vitals(self._metrics_cache, self.settings)
            return Observation(success=True, data=vitals.model_dump())
        except Exception as e:
            logger.error(f"Telemetry fetch_metrics failed: {e}")
            return Observation(success=False, error=str(e))

    async def _increment_counter(self, params: dict[str, Any]) -> Observation:
        name = params.get("name")
        labels = params.get("labels", {})

        try:
            if name == "negotiation_total":
                negotiation_total.labels(**labels).inc()
            elif name == "negotiation_accepted_total":
                negotiation_accepted_total.labels(**labels).inc()
            else:
                return Observation(success=False, error=f"Unknown counter: {name}")

            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))
