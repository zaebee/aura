import json
import os
import subprocess  # nosec
from pathlib import Path
from typing import Any

import httpx
import structlog

from src.config import KeeperSettings
from src.dna import BeeContext

logger = structlog.get_logger(__name__)


class BeeAggregator:
    """A - Aggregator: Gathers signals from Git, Prometheus, and Filesystem."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.prometheus_url = settings.prometheus_url
        self.repo_name = settings.github_repository
        self.event_path = settings.github_event_path

    async def perceive(self) -> BeeContext:
        logger.info("bee_aggregator_perceive_started")

        git_diff = await self._get_git_diff()
        hive_metrics = await self._get_hive_metrics()
        filesystem_map = self._scan_filesystem()
        event_data = self._load_event_data()

        return BeeContext(
            git_diff=git_diff,
            hive_metrics=hive_metrics,
            filesystem_map=filesystem_map,
            repo_name=self.repo_name,
            event_name=self.settings.github_event_name,
            event_data=event_data,
        )

    async def _get_git_diff(self) -> str:
        try:
            # Try to get diff between HEAD~1 and HEAD
            result = subprocess.run(
                ["git", "diff", "--unified=0", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                check=False
            ) # nosec
            if result.returncode == 0:
                return result.stdout

            # Fallback for shallow clones or initial commit
            result = subprocess.run(
                ["git", "show", "--unified=0", "HEAD"],
                capture_output=True,
                text=True,
                check=False
            ) # nosec
            return result.stdout
        except Exception as e:
            logger.warning("git_diff_failed", error=str(e))
            return ""

    async def _get_hive_metrics(self) -> dict[str, Any]:
        query = 'sum(rate(negotiation_accepted_total[5m])) / sum(rate(negotiation_total[5m]))'
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query}
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
        root_path = Path("../../")
        for path in root_path.rglob("*.py"):
            if ".venv" not in path.parts and "proto" not in path.parts:
                # Store path relative to root
                rel_path = path.relative_to(root_path)
                filesystem_map.append(str(rel_path))
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
