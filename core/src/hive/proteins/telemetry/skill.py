import logging
from typing import Any

from aura_core import SkillProtocol
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import Observation

from config.server import ServerSettings

from .engine import (
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
    """

    def __init__(self) -> None:
        self.settings: ServerSettings | None = None
        self.provider: Any = None
        self._metrics_cache = MetricsCache(ttl_seconds=30)
        self._capabilities = {
            "fetch_metrics": self._fetch_metrics,
            "get_vitals": self._fetch_metrics,
            "health_check": self._health_check,
            "increment_counter": self._increment_counter,
        }

    def get_name(self) -> str:
        return "telemetry"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: ServerSettings, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Telemetry skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _fetch_metrics(self, params: dict[str, Any]) -> Observation:
        from datetime import datetime

        vitals = await fetch_vitals(self._metrics_cache, self.settings)
        data = vitals.to_dict()
        # Ensure timestamp is string for Struct compatibility
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return Observation(success=True, metadata=protobuf.Struct().from_dict(data))

    async def _health_check(self, params: dict[str, Any]) -> Observation:
        return Observation(
            success=True, metadata=protobuf.Struct().from_dict({"status": "healthy"})
        )

    async def _increment_counter(self, params: dict[str, Any]) -> Observation:
        p = MetricIncrementParams(**params)
        if p.name == "negotiation_total":
            negotiation_total.labels(**p.labels).inc()
        elif p.name == "negotiation_accepted_total":
            negotiation_accepted_total.labels(**p.labels).inc()
        else:
            return Observation(success=False, error=f"Unknown counter: {p.name}")
        return Observation(success=True)
