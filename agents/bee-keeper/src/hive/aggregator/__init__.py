import asyncio
import json
import os
import subprocess  # nosec
from typing import Any, cast

import betterproto
import httpx
import litellm
from datetime import UTC, datetime

import structlog

from config import KeeperSettings
from aura_core import Aggregator, find_hive_root, make_struct
from aura_core_gen.aura.core.v1 import (
    Context,
    ContextType,
    BeeContextData,
    SystemVitals,
    Event,
)

logger = structlog.get_logger(__name__)


class BeeAggregator(Aggregator[Any, Context]):
    """A - Aggregator: Gathers signals from NATS, Loki, and Prometheus."""

    async def get_vitals(self) -> SystemVitals:
        """Proprioception for the BeeKeeper."""
        return SystemVitals(
            status="ok",
            timestamp=datetime.now(UTC),
        )

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.prometheus_url = settings.prometheus_url
        self.repo_name = settings.github_repository
        self.event_path = settings.github_event_path
        self.brain_status: dict[str, bool] = {}

    async def perceive(self, signal: Any, **kwargs: Any) -> Context:
        event_name = kwargs.get("event_name", "manual")
        logger.info("bee_aggregator_perceive_started", trigger_event=event_name)

        error_msg = ""
        source = "unknown"

        # 1. Parse Inbound Signal (Event)
        if isinstance(signal, bytes):
            try:
                event = Event().parse(signal)
                name, val = betterproto.which_one_of(event, "payload")
                if name == "alert" and val:
                    error_msg = val.message
                    source = val.source
                elif name == "log" and val:
                    error_msg = val.message
                    source = val.worker_name
            except Exception as e:
                logger.warning("failed_to_parse_event", error=str(e))
                error_msg = str(signal)
        elif isinstance(signal, str):
            error_msg = signal

        # 2. Gather System Context
        vitals = await self._get_vitals_summary()
        logs = await self._get_recent_logs(source)

        context = Context(
            identifier=self.repo_name or "hive-bee-keeper",
            context_type=cast(ContextType, ContextType.CONTEXT_TYPE_BEE),
            bee=BeeContextData(
                repo_name=self.repo_name or "hive",
                error_message=error_msg,
                error_source=source,
                # Keep legacy fields for backward compatibility if needed, but error_message/source are preferred
                git_diff=error_msg,
                filesystem_map=[source],
            ),
            metadata=make_struct(
                {
                    "event_name": str(event_name),
                    "brain_status": self.brain_status,
                    "vitals": vitals,
                    "recent_logs": logs,
                }
            ),
        )
        return context

    async def _get_vitals_summary(self) -> dict[str, Any]:
        """Fetch current CPU/Mem and Pod health."""
        queries = {
            "cpu": 'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100',
            "memory": 'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024',
            "unhealthy_pods": 'count(kube_pod_status_phase{namespace="default", phase!="Running"} > 0) or vector(0)',
        }

        vitals = {"cpu": 0.0, "memory": 0.0, "unhealthy_pods": 0}
        keys = list(queries.keys())

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resps = await asyncio.gather(
                    *[
                        client.get(
                            f"{self.settings.prometheus_url}/api/v1/query",
                            params={"query": q},
                        )
                        for q in queries.values()
                    ],
                    return_exceptions=True,
                )

                for i, key in enumerate(keys):
                    resp = resps[i]
                    if isinstance(resp, httpx.Response) and resp.status_code == 200:
                        try:
                            r = resp.json()
                            if r.get("data", {}).get("result"):
                                value_str = r["data"]["result"][0]["value"][1]
                                vitals[key] = (
                                    int(float(value_str))
                                    if key == "unhealthy_pods"
                                    else float(value_str)
                                )
                        except (KeyError, IndexError, ValueError) as e:
                            logger.warning(
                                "prometheus_parse_failed", key=key, error=str(e)
                            )
                    elif isinstance(resp, Exception):
                        logger.warning(
                            "prometheus_query_failed", key=key, error=str(resp)
                        )
        except Exception as e:
            logger.warning("vitals_gathering_failed", error=str(e))
        return vitals

    async def _get_recent_logs(self, source: str) -> str:
        """Fetch last 20 lines of logs from Loki for the source."""
        if not self.settings.loki_url:
            return "Loki not configured."

        query = f'{{job=~".*{source}.*"}}'
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.settings.loki_url}/loki/api/v1/query_range",
                    params={"query": query, "limit": 20},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    lines = []
                    for stream in data.get("data", {}).get("result", []):
                        for val in stream.get("values", []):
                            lines.append(val[1])
                    return "\n".join(lines[-20:])
        except Exception as e:
            logger.warning("loki_logs_failed", error=str(e))
        return "No logs found."

    async def _get_git_diff(self) -> str:
        try:
            # Try to get diff between HEAD~1 and HEAD, excluding meta files
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--unified=0",
                    "HEAD~1",
                    "HEAD",
                    "--",
                    ".",
                    ":!HIVE_STATE.md",
                    ":!CHRONICLES.md",
                    ":!llms.txt",
                ],
                capture_output=True,
                text=True,
                check=False,
            )  # nosec
            if result.returncode == 0:
                return result.stdout

            # Fallback for shallow clones or initial commit
            result = subprocess.run(
                [
                    "git",
                    "show",
                    "--unified=0",
                    "HEAD",
                    "--",
                    ".",
                    ":!HIVE_STATE.md",
                    ":!CHRONICLES.md",
                    ":!llms.txt",
                ],
                capture_output=True,
                text=True,
                check=False,
            )  # nosec
            return result.stdout
        except Exception as e:
            logger.warning("git_diff_failed", error=str(e))
            return ""

    async def _get_hive_metrics(self) -> dict[str, Any]:
        query = "sum(rate(negotiation_accepted_total[5m])) / sum(rate(negotiation_total[5m]))"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query", params={"query": query}
                )
                response.raise_for_status()
                data = response.json()
                if data["status"] == "success" and data["data"]["result"]:
                    success_rate = float(data["data"]["result"][0]["value"][1])
                    return {"negotiation_success_rate": success_rate}
        except Exception as e:
            logger.warning("prometheus_query_failed", error=str(e))

        return {"negotiation_success_rate": 0.0, "status": "UNKNOWN"}

    def _scan_filesystem(self) -> list[str]:
        filesystem_map = []
        # Scan from repository root
        root_path = find_hive_root()

        # 1. Capture Root Structure (Top-level only) for Macro-ATCG check
        for path in root_path.iterdir():
            rel_path = path.relative_to(root_path)
            filesystem_map.append(str(rel_path))

        # 2. Capture all .py files recursively for deeper audits
        for path in root_path.rglob("*.py"):
            if ".venv" not in path.parts and "proto" not in path.parts:
                # Store path relative to root
                rel_path = path.relative_to(root_path)
                rel_path_str = str(rel_path)
                if rel_path_str not in filesystem_map:
                    filesystem_map.append(rel_path_str)
        return filesystem_map

    def _load_event_data(self) -> dict[str, Any]:
        if self.event_path and os.path.exists(self.event_path):
            try:
                with open(self.event_path) as f:
                    data: dict[str, Any] = json.load(f)
                    return data
            except Exception as e:
                logger.warning("event_data_load_failed", error=str(e))
        return {}

    async def test_brain_connectivity(self) -> bool:
        """Pings the LLM endpoints to verify connectivity."""
        logger.info("testing_brain_connectivity")
        models = {
            "primary": self.settings.llm__model,
            "fallback": self.settings.llm__fallback_model,
        }
        # Reset status and ensure we have entries for both roles
        self.brain_status = {role: False for role in models}

        for role, model in models.items():
            if not model:
                continue
            try:
                logger.info("pinging_llm", role=role, model=model)

                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                    "timeout": 10.0,
                    "api_key": self.settings.llm__api_key,
                }

                if "ollama" in model:
                    kwargs["api_base"] = self.settings.llm__ollama_base_url

                # Simple completion to test connectivity via LiteLLM
                await litellm.acompletion(**kwargs)

                logger.info("llm_ping_success", role=role, model=model)
                self.brain_status[role] = True
            except Exception as e:
                # Log as warning to ensure the Hive doesn't exit prematurely if at least one model is alive
                logger.warning("llm_ping_failed", role=role, model=model, error=str(e))

        return any(self.brain_status.values())
