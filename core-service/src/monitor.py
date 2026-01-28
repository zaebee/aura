"""
Prometheus metrics monitoring with caching layer.

Queries Prometheus for cluster health metrics (CPU, memory) with 30-second
caching to reduce load on Prometheus.
"""

import time
from datetime import datetime
from typing import Any

import httpx
import structlog

from config import get_settings

logger = structlog.get_logger(__name__)


class MetricsCache:
    """Thread-safe cache for Prometheus metrics with TTL."""

    def __init__(self, ttl_seconds: int = 30):
        """
        Initialize metrics cache.

        Args:
            ttl_seconds: Time-to-live for cached data in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, Any] = {}
        self._timestamp: float = 0.0

    def get(self) -> dict[str, Any] | None:
        """
        Retrieve cached metrics if not expired.

        Returns:
            Cached metrics dict or None if expired/empty
        """
        if not self._cache:
            return None

        age = time.time() - self._timestamp
        if age > self.ttl_seconds:
            logger.debug("cache_expired", age_seconds=age)
            return None

        logger.debug("cache_hit", age_seconds=age)
        return self._cache

    def set(self, metrics: dict[str, Any]) -> None:
        """
        Store metrics in cache with current timestamp.

        Args:
            metrics: Metrics dictionary to cache
        """
        self._cache = metrics
        self._timestamp = time.time()
        logger.debug("cache_updated", timestamp=self._timestamp)


# Global cache instance
_metrics_cache = MetricsCache(ttl_seconds=30)


async def get_hive_metrics() -> dict[str, Any]:
    """
    Query Prometheus for cluster health metrics.

    Queries CPU and memory usage for the default namespace with 30-second
    caching to reduce load on Prometheus.

    Returns:
        Dictionary containing:
        - status: "ok" or "error"
        - cpu_usage_percent: Average CPU usage percentage
        - memory_usage_mb: Average memory usage in MB
        - timestamp: ISO 8601 timestamp
        - cached: Whether data was served from cache

    Error Handling:
        - Connection failures: Return cached data or error dict
        - Timeouts: Return cached data or error dict (5s timeout)
        - Parse errors: Return error dict
    """
    settings = get_settings()

    # Check cache first
    cached = _metrics_cache.get()
    if cached:
        cached["cached"] = True
        return cached

    # Query Prometheus
    cpu_query = 'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100'
    mem_query = (
        'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024'
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Query CPU
            cpu_response = await client.get(
                f"{settings.prometheus_url}/api/v1/query",
                params={"query": cpu_query},
            )
            cpu_response.raise_for_status()
            cpu_data = cpu_response.json()

            # Query Memory
            mem_response = await client.get(
                f"{settings.prometheus_url}/api/v1/query",
                params={"query": mem_query},
            )
            mem_response.raise_for_status()
            mem_data = mem_response.json()

            # Extract values
            cpu_usage = 0.0
            mem_usage = 0.0

            if cpu_data.get("status") == "success" and cpu_data.get("data", {}).get(
                "result"
            ):
                cpu_usage = float(cpu_data["data"]["result"][0]["value"][1])

            if mem_data.get("status") == "success" and mem_data.get("data", {}).get(
                "result"
            ):
                mem_usage = float(mem_data["data"]["result"][0]["value"][1])

            metrics = {
                "status": "ok",
                "cpu_usage_percent": round(cpu_usage, 2),
                "memory_usage_mb": round(mem_usage, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "cached": False,
            }

            # Update cache
            _metrics_cache.set(metrics)

            logger.info(
                "prometheus_query_success",
                cpu_percent=metrics["cpu_usage_percent"],
                memory_mb=metrics["memory_usage_mb"],
            )

            return metrics

    except httpx.TimeoutException as e:
        logger.error("prometheus_timeout", error=str(e), timeout_seconds=5)
        # Return cached data if available
        cached = _metrics_cache.get()
        if cached:
            logger.warning("returning_stale_cache_after_timeout")
            cached["cached"] = True
            return cached

        return {
            "status": "error",
            "cpu_usage_percent": 0.0,
            "memory_usage_mb": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
            "cached": False,
            "error": "Prometheus timeout",
        }

    except httpx.ConnectError as e:
        logger.error("prometheus_connection_error", error=str(e))
        # Return cached data if available
        cached = _metrics_cache.get()
        if cached:
            logger.warning("returning_stale_cache_after_connection_error")
            cached["cached"] = True
            return cached

        return {
            "status": "error",
            "cpu_usage_percent": 0.0,
            "memory_usage_mb": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
            "cached": False,
            "error": "Prometheus unavailable",
        }

    except (ValueError, KeyError, IndexError) as e:
        logger.error("prometheus_parse_error", error=str(e), exc_info=True)
        return {
            "status": "error",
            "cpu_usage_percent": 0.0,
            "memory_usage_mb": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
            "cached": False,
            "error": "Failed to parse Prometheus response",
        }

    except Exception as e:
        logger.error("prometheus_unexpected_error", error=str(e), exc_info=True)
        # Return cached data if available
        cached = _metrics_cache.get()
        if cached:
            logger.warning("returning_stale_cache_after_unexpected_error")
            cached["cached"] = True
            return cached

        return {
            "status": "error",
            "cpu_usage_percent": 0.0,
            "memory_usage_mb": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
            "cached": False,
            "error": str(e),
        }
