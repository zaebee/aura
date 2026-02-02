import json
import os
import subprocess  # nosec
from typing import Any

import httpx
import litellm
import structlog
from aura_core.dna import BeeContext, find_hive_root

from .metabolism.config import KeeperSettings

logger = structlog.get_logger(__name__)


class BeeAggregator:
    """A - Aggregator: Gathers signals from Git, Prometheus, and Filesystem."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.prometheus_url = settings.prometheus_url
        self.repo_name = settings.github_repository
        self.event_path = settings.github_event_path
        self.brain_status: dict[str, bool] = {}

    async def sense(self, event_name: str = "manual") -> BeeContext:
        logger.info("bee_aggregator_sense_started", trigger_event=event_name)

        git_diff = await self._get_git_diff()
        hive_metrics = await self._get_hive_metrics()
        filesystem_map = self._scan_filesystem()
        event_data = self._load_event_data()

        return BeeContext(
            git_diff=git_diff,
            hive_metrics=hive_metrics,
            filesystem_map=filesystem_map,
            repo_name=self.repo_name,
            event_name=event_name,
            event_data=event_data,
            metadata={"brain_status": self.brain_status},
        )

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
