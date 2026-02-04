import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from aura_core import SystemVitals

logger = structlog.get_logger(__name__)


class MetricsCache:
    """A simple in-memory cache for Prometheus metrics with a TTL."""

    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, Any] = {}
        self._timestamp: float = 0.0

    def get(self, ignore_ttl: bool = False) -> dict[str, Any] | None:
        if not self._cache:
            return None
        if not ignore_ttl:
            age = time.time() - self._timestamp
            if age > self.ttl_seconds:
                return None
        return self._cache

    def set(self, metrics: dict[str, Any]) -> None:
        self._cache = metrics
        self._timestamp = time.time()


async def fetch_vitals(metrics_cache: MetricsCache, settings: Any) -> SystemVitals:
    """Standardized proprioception (self-healing metrics)."""
    cached = metrics_cache.get()
    if cached:
        return SystemVitals(**{**cached, "cached": True})

    cpu_query = (
        'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100'
    )
    mem_query = (
        'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024'
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            base_url = str(settings.server.prometheus_url).rstrip("/")
            responses = await asyncio.gather(
                client.get(f"{base_url}/api/v1/query", params={"query": cpu_query}),
                client.get(f"{base_url}/api/v1/query", params={"query": mem_query}),
                return_exceptions=True,
            )
            errors: list[str] = []
            cpu_usage, cpu_success = process_metric_response(
                responses[0], "cpu", errors
            )
            mem_usage, mem_success = process_metric_response(
                responses[1], "mem", errors
            )

            if not (cpu_success or mem_success):
                # Self-Healing: If Prometheus is down, try to fallback to stale cache
                error_msg = f"All metric fetches failed: {', '.join(errors)}"
                cached_dict = metrics_cache.get(ignore_ttl=True)
                if cached_dict:
                    return SystemVitals(
                        **{
                            **cached_dict,
                            "cached": True,
                            "error": f"Stale data due to: {error_msg}",
                        }
                    )
                return SystemVitals(
                    status="unstable",
                    timestamp=datetime.now(UTC).isoformat(),
                    error=error_msg,
                )

            metrics_dict = {
                "status": "ok",
                "cpu_usage_percent": round(cpu_usage, 2),
                "memory_usage_mb": round(mem_usage, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "cached": False,
            }
            if errors:
                metrics_dict["status"] = "PARTIAL"
                metrics_dict["warnings"] = errors

            metrics_cache.set(metrics_dict)
            return SystemVitals(**metrics_dict)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("monitoring_failure", error=error_msg)
        cached_dict = metrics_cache.get(ignore_ttl=True)
        if cached_dict:
            return SystemVitals(
                **{
                    **cached_dict,
                    "cached": True,
                    "error": f"Stale data due to: {error_msg}",
                }
            )
        return SystemVitals(
            status="unstable",
            timestamp=datetime.now(UTC).isoformat(),
            error=error_msg,
        )


def process_metric_response(
    response: Any, metric_name: str, errors: list[str]
) -> tuple[float, bool]:
    if isinstance(response, httpx.Response):
        try:
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results and len(results[0].get("value", [])) > 1:
                    return float(results[0]["value"][1]), True
            errors.append(f"{metric_name}_no_data")
        except Exception:
            errors.append(f"{metric_name}_parse_error")
    else:
        errors.append(f"{metric_name}_fetch_error")
    return 0.0, False
