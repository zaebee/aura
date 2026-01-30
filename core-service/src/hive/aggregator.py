import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from hive.dna import HiveContext
from sqlalchemy.exc import SQLAlchemyError

from config import get_settings
from db import InventoryItem, SessionLocal

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


class HiveAggregator:
    """A - Aggregator: Consolidates database and system health signals."""

    def __init__(self):
        self.settings = get_settings()
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def _resolve_brain_path(self) -> str:
        """
        Ensure aura_brain.json path is resolved relative to the package root,
        looking in both /app/src/ and ./src/.
        """
        search_paths = [
            Path("/app/src/aura_brain.json"),
            Path("./src/aura_brain.json"),
            Path(__file__).parent.parent / "aura_brain.json",
        ]

        # Also check setting path
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.insert(0, Path(self.settings.llm.compiled_program_path))

        for path in search_paths:
            try:
                if path.exists():
                    return str(path.absolute())
            except Exception:
                continue

        return "UNKNOWN"

    async def get_system_metrics(self) -> dict[str, Any]:
        """
        Refactored monitor.py logic. Queries Prometheus with self-healing.
        """
        # 1. Check Cache
        cached = self._metrics_cache.get()
        if cached:
            return {**cached, "cached": True}

        # 2. Query Prometheus
        cpu_query = 'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100'
        mem_query = 'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024'

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                base_url = str(self.settings.server.prometheus_url).rstrip("/")
                cpu_task = client.get(f"{base_url}/api/v1/query", params={"query": cpu_query})
                mem_task = client.get(f"{base_url}/api/v1/query", params={"query": mem_query})

                responses = await asyncio.gather(cpu_task, mem_task, return_exceptions=True)

                # Check for exceptions in gather
                for resp in responses:
                    if isinstance(resp, Exception):
                        raise resp

                cpu_resp, mem_resp = responses
                cpu_resp.raise_for_status()
                mem_resp.raise_for_status()

                cpu_data = cpu_resp.json()
                mem_data = mem_resp.json()

                cpu_usage = 0.0
                if cpu_data.get("status") == "success" and cpu_data.get("data", {}).get("result"):
                    cpu_usage = float(cpu_data["data"]["result"][0]["value"][1])

                mem_usage = 0.0
                if mem_data.get("status") == "success" and mem_data.get("data", {}).get("result"):
                    mem_usage = float(mem_data["data"]["result"][0]["value"][1])

                metrics = {
                    "status": "ok",
                    "cpu_usage_percent": round(cpu_usage, 2),
                    "memory_usage_mb": round(mem_usage, 2),
                    "timestamp": datetime.utcnow().isoformat(),
                    "cached": False,
                }
                self._metrics_cache.set(metrics)
                return metrics

        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException, asyncio.TimeoutError) as e:
            logger.error("prometheus_unreachable", error=str(e))
            # Self-healing: Return cached if available (even if expired), else UNKNOWN
            cached = self._metrics_cache.get(ignore_ttl=True)
            if cached:
                return {**cached, "cached": True, "warning": "stale_data"}

            return {
                "status": "UNKNOWN",
                "cpu_usage_percent": 0.0,
                "memory_usage_mb": 0.0,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
        except Exception as e:
            logger.error("prometheus_unexpected_error", error=str(e))
            return {"status": "UNKNOWN", "error": "unexpected_error"}

    async def perceive(self, signal: Any) -> HiveContext:
        """
        Extract data from the inbound signal and enrich it with system state.
        """
        item_id = signal.item_id
        bid_amount = signal.bid_amount
        agent_did = signal.agent.did
        reputation = signal.agent.reputation_score
        request_id = getattr(signal, "request_id", "")

        logger.debug("aggregator_perceive_started", item_id=item_id, request_id=request_id)

        # 1. Fetch item data
        def fetch_item_sync():
            with SessionLocal() as session:
                return session.query(InventoryItem).filter_by(id=item_id).first()

        item_data = {}
        try:
            item = await asyncio.to_thread(fetch_item_sync)
            if item:
                item_data = {
                    "name": item.name,
                    "base_price": item.base_price,
                    "floor_price": item.floor_price,
                    "meta": item.meta or {},
                }
            else:
                logger.warning("item_not_found", item_id=item_id)
        except SQLAlchemyError as e:
            logger.error("aggregator_db_error", error=str(e))

        # 2. Fetch system health (Self-healing logic integrated)
        system_health = await self.get_system_metrics()

        # 3. Resolve Brain Path
        brain_path = self._resolve_brain_path()

        return HiveContext(
            item_id=item_id,
            bid_amount=bid_amount,
            agent_did=agent_did,
            reputation=reputation,
            item_data=item_data,
            system_health=system_health,
            request_id=request_id,
            metadata={"brain_path": brain_path},
        )
