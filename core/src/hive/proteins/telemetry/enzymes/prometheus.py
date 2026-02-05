import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import structlog
from aura_core import SystemVitals
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import REGISTRY, Counter

logger = structlog.get_logger(__name__)

# --- Metrics Implementation ---


def _get_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    if name in REGISTRY._names_to_collectors:
        return cast(Counter, REGISTRY._names_to_collectors[name])
    return Counter(name, documentation, labelnames)


negotiation_total = _get_counter("negotiation_total", "Total negotiations", ["service"])
negotiation_accepted_total = _get_counter(
    "negotiation_accepted_total", "Total accepted", ["service"]
)
heartbeat_total = _get_counter("heartbeat_total", "Total heartbeats", ["service"])

# --- Telemetry Implementation ---


def init_telemetry(
    service_name: str, otlp_endpoint: str = "http://jaeger:4317"
) -> trace.Tracer:
    service_name = service_name.lower().strip()
    if not service_name:
        raise ValueError("service_name required")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    except Exception as e:
        logging.warning(f"OTLP failed, console fallback: {e}")
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


# --- Vitals Implementation ---


class MetricsCache:
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, Any] = {}
        self._timestamp: float = 0.0

    def get(self, ignore_ttl: bool = False) -> dict[str, Any] | None:
        if not self._cache:
            return None
        if not ignore_ttl and (time.time() - self._timestamp > self.ttl_seconds):
            return None
        return self._cache

    def set(self, metrics: dict[str, Any]) -> None:
        self._cache = metrics
        self._timestamp = time.time()


async def fetch_vitals(metrics_cache: MetricsCache, settings: Any) -> SystemVitals:
    cached = metrics_cache.get()
    if cached:
        return SystemVitals(**{**cached, "cached": True})

    cpu_q = (
        'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100'
    )
    mem_q = 'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024'

    # DNA Rule: Proteins must not import global settings.
    if not settings:
        raise ValueError("SystemVitals fetch failed: settings not provided")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Handle both global settings and sub-config (for flexibility)
            if hasattr(settings, "prometheus_url"):
                base_url = str(settings.prometheus_url).rstrip("/")
            elif hasattr(settings, "server"):
                base_url = str(settings.server.prometheus_url).rstrip("/")
            else:
                raise ValueError("Settings object missing prometheus_url")

            resps = await asyncio.gather(
                client.get(f"{base_url}/api/v1/query", params={"query": cpu_q}),
                client.get(f"{base_url}/api/v1/query", params={"query": mem_q}),
                return_exceptions=True,
            )
            errs: list[str] = []
            cpu, cpu_ok = process_resp(resps[0], "cpu", errs)
            mem, mem_ok = process_resp(resps[1], "mem", errs)

            if not (cpu_ok or mem_ok):
                e_msg = f"Metric fetch failed: {', '.join(errs)}"
                cached_dict = metrics_cache.get(ignore_ttl=True)
                if cached_dict:
                    return SystemVitals(
                        **{
                            **cached_dict,
                            "cached": True,
                            "error": f"Stale data due to: {e_msg}",
                        }
                    )
                return SystemVitals(
                    status="unstable",
                    timestamp=datetime.now(UTC).isoformat(),
                    error=e_msg,
                )

            m_dict = {
                "status": "ok",
                "cpu_usage_percent": round(cpu, 2),
                "memory_usage_mb": round(mem, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "cached": False,
            }
            if errs:
                m_dict["status"] = "PARTIAL"
                m_dict["warnings"] = errs  # type: ignore
            metrics_cache.set(m_dict)
            return SystemVitals(**m_dict)
    except Exception as e:
        logger.error("monitoring_failure", error=str(e))
        e_msg = f"{type(e).__name__}: {str(e)}"
        cached_dict = metrics_cache.get(ignore_ttl=True)
        if cached_dict:
            return SystemVitals(
                **{
                    **cached_dict,
                    "cached": True,
                    "error": f"Stale data due to: {e_msg}",
                }
            )
        return SystemVitals(
            status="unstable", timestamp=datetime.now(UTC).isoformat(), error=e_msg
        )


def process_resp(resp: Any, name: str, errs: list[str]) -> tuple[float, bool]:
    if isinstance(resp, httpx.Response) and resp.status_code == 200:
        try:
            val = resp.json()["data"]["result"][0]["value"][1]
            return float(val), True
        except (KeyError, IndexError):
            errs.append(f"{name}_no_data")
    else:
        errs.append(f"{name}_fetch_error")
    return 0.0, False
