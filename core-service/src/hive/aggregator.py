import asyncio
import time
from datetime import UTC, datetime
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
        search_paths = []

        # Priority 1: Explicitly configured path
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.append(Path(self.settings.llm.compiled_program_path))

        # Priority 2: Standard expected locations
        search_paths.extend([
            Path("/app/src/aura_brain.json"),
            Path("./src/aura_brain.json"),
            Path(__file__).parent.parent / "aura_brain.json",
        ])

        for path in search_paths:
            try:
                # Check if it's a file and exists
                if path.exists() and path.is_file():
                    return str(path.absolute())
            except OSError:
                continue

        return "UNKNOWN"

    async def get_system_metrics(self) -> dict[str, Any]:
        """
        Refactored monitor.py logic. Queries Prometheus with self-healing.
        Ensures Partial Context: returns whatever metrics are available.
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

                cpu_usage = 0.0
                mem_usage = 0.0
                any_success = False
                errors = []

                # Process CPU Response
                cpu_res = responses[0]
                if isinstance(cpu_res, httpx.Response):
                    try:
                        cpu_res.raise_for_status()
                        cpu_data = cpu_res.json()
                        if cpu_data.get("status") == "success":
                            results = cpu_data.get("data", {}).get("result", [])
                            if results and len(results[0].get("value", [])) > 1:
                                cpu_usage = float(results[0]["value"][1])
                                any_success = True
                        else:
                            errors.append(f"cpu_api_status_{cpu_data.get('status')}")
                    except Exception as e:
                        errors.append(f"cpu_parse_error_{type(e).__name__}")
                else:
                    errors.append(f"cpu_fetch_error_{type(cpu_res).__name__}")

                # Process Memory Response
                mem_res = responses[1]
                if isinstance(mem_res, httpx.Response):
                    try:
                        mem_res.raise_for_status()
                        mem_data = mem_res.json()
                        if mem_data.get("status") == "success":
                            results = mem_data.get("data", {}).get("result", [])
                            if results and len(results[0].get("value", [])) > 1:
                                mem_usage = float(results[0]["value"][1])
                                any_success = True
                        else:
                            errors.append(f"mem_api_status_{mem_data.get('status')}")
                    except Exception as e:
                        errors.append(f"mem_parse_error_{type(e).__name__}")
                else:
                    errors.append(f"mem_fetch_error_{type(mem_res).__name__}")

                # If both failed completely, fallback to exception handler
                if not any_success:
                    raise httpx.ConnectError(f"All metric fetches failed: {', '.join(errors)}")

                metrics = {
                    "status": "ok",
                    "cpu_usage_percent": round(cpu_usage, 2),
                    "memory_usage_mb": round(mem_usage, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "cached": False,
                }

                # Include warnings if partial success
                if errors:
                    metrics["status"] = "PARTIAL"
                    metrics["warnings"] = errors

                self._metrics_cache.set(metrics)
                return metrics

        except (TimeoutError, httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error("prometheus_unreachable", error=str(e))
            # Self-healing: Return cached if available (even if expired), else UNKNOWN
            cached = self._metrics_cache.get(ignore_ttl=True)
            if cached:
                return {**cached, "cached": True, "warning": "stale_data", "error": str(e)}

            return {
                "status": "UNKNOWN",
                "cpu_usage_percent": 0.0,
                "memory_usage_mb": 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e)
            }
        except Exception as e:
            logger.error("prometheus_unexpected_error", error=str(e))
            return {"status": "UNKNOWN", "error": "unexpected_error", "detail": str(e)}

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
