import logging
from typing import Any

from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.server import ServerSettings

from .engine import (
    MetricsCache,
    check_k8s_health,
    fetch_vitals,
    negotiation_accepted_total,
    negotiation_total,
    query_loki,
    query_prometheus,
)
from .schema import (
    K8sHealthParams,
    LokiQueryParams,
    MetricIncrementParams,
    PrometheusQueryParams,
)

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
            "query_loki": self._query_loki,
            "query_prometheus": self._query_prometheus,
            "health_check_k8s": self._health_check_k8s,
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
        return Observation(success=True, metadata=make_struct(data))

    async def _health_check(self, params: dict[str, Any]) -> Observation:
        return Observation(success=True, metadata=make_struct({"status": "healthy"}))

    async def _increment_counter(self, params: dict[str, Any]) -> Observation:
        p = MetricIncrementParams(**params)
        if p.name == "negotiation_total":
            negotiation_total.labels(**p.labels).inc()
        elif p.name == "negotiation_accepted_total":
            negotiation_accepted_total.labels(**p.labels).inc()
        else:
            return Observation(success=False, error=f"Unknown counter: {p.name}")
        return Observation(success=True)

    async def _query_loki(self, params: dict[str, Any]) -> Observation:
        p = LokiQueryParams(**params)
        results = await query_loki(p.query, p.limit, self.settings)
        return Observation(success=True, metadata=make_struct({"results": results}))

    async def _query_prometheus(self, params: dict[str, Any]) -> Observation:
        p = PrometheusQueryParams(**params)
        result = await query_prometheus(p.query, self.settings)
        return Observation(success=True, metadata=make_struct(result))

    async def _health_check_k8s(self, params: dict[str, Any]) -> Observation:
        p = K8sHealthParams(**params)
        result = await check_k8s_health(p.namespace, self.settings)
        return Observation(success=True, metadata=make_struct(result))
