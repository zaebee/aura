import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config.server import ServerSettings

from .enzymes.prometheus import (
    MetricsCache,
    fetch_vitals,
    negotiation_accepted_total,
    negotiation_total,
)
from .schema import MetricIncrementParams

logger = logging.getLogger(__name__)


class TelemetrySkill(SkillProtocol[ServerSettings, Any, dict[str, Any], Observation]):
    """
    Telemetry Protein: Handles system metrics and health checks.
    Standardized following the Crystalline Protein Standard and Enzyme pattern.
    """

    def __init__(self) -> None:
        self.settings: ServerSettings | None = None
        self.provider: Any = None
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def get_name(self) -> str:
        return "telemetry"

    def get_capabilities(self) -> list[str]:
        return ["fetch_metrics", "health_check", "increment_counter", "get_vitals"]

    def bind(self, settings: ServerSettings, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        try:
            if intent in ["fetch_metrics", "get_vitals"]:
                vitals = await fetch_vitals(self._metrics_cache, self.settings)
                return Observation(success=True, data=vitals.model_dump())

            elif intent == "health_check":
                return Observation(success=True, data={"status": "healthy"})

            elif intent == "increment_counter":
                p = MetricIncrementParams(**params)
                if p.name == "negotiation_total":
                    negotiation_total.labels(**p.labels).inc()
                elif p.name == "negotiation_accepted_total":
                    negotiation_accepted_total.labels(**p.labels).inc()
                else:
                    return Observation(
                        success=False, error=f"Unknown counter: {p.name}"
                    )
                return Observation(success=True)

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            logger.error(f"Telemetry skill error: {e}")
            return Observation(success=False, error=str(e))
