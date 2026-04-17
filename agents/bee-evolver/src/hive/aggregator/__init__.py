import subprocess  # nosec
from pathlib import Path
from typing import Any

import httpx
import structlog

from config import EvolverSettings
from aura_core import find_hive_root
from ..models import HiveContext

logger = structlog.get_logger(__name__)

_GITHUB_API = "https://api.github.com"


class EvolverAggregator:
    """A - Aggregator: Senses the current state of the Hive."""

    def __init__(self, settings: EvolverSettings) -> None:
        self.settings = settings
        self._root: Path = find_hive_root()

    async def perceive(self) -> HiveContext:
        logger.info("evolver_aggregator_perceive_started")

        git_log = self._get_git_log()
        hive_state = self._read_hive_state()
        keeper_prompt = self._read_keeper_prompt()
        filesystem_map = self._scan_filesystem()
        recent_heresies = self._extract_recent_heresies(hive_state)

        open_issues: list[dict] = []
        open_prs: list[dict] = []
        if self.settings.github_token and self.settings.github_token != "mock":  # nosec B105
            async with httpx.AsyncClient(timeout=15.0) as client:
                open_issues = await self._fetch_issues(client)
                open_prs = await self._fetch_prs(client)

        ctx = HiveContext(
            git_log=git_log,
            hive_state=hive_state,
            open_issues=open_issues,
            open_prs=open_prs,
            filesystem_map=filesystem_map,
            keeper_prompt=keeper_prompt,
            recent_heresies=recent_heresies,
            focus_hint=self.settings.evolver_focus,
        )
        logger.info(
            "evolver_aggregator_perceive_done",
            issues=len(open_issues),
            prs=len(open_prs),
            heresies=len(recent_heresies),
        )
        return ctx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_git_log(self) -> str:
        try:
            result = subprocess.run(  # nosec
                ["git", "log", "--oneline", "-20"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self._root),
            )
            return result.stdout.strip()
        except Exception as e:
            logger.warning("git_log_failed", error=str(e))
            return ""

    def _read_hive_state(self) -> str:
        path = self._root / "HIVE_STATE.md"
        if path.exists():
            return path.read_text()
        return ""

    def _read_keeper_prompt(self) -> str:
        path = self._root / "agents/bee-keeper/prompts/bee_keeper.md"
        if path.exists():
            return path.read_text()
        return ""

    def _scan_filesystem(self) -> list[str]:
        exclude = set(self.settings.exclude_dirs)
        items: list[str] = []
        for p in self._root.rglob("*"):
            # Skip any path whose parts contain an excluded directory name
            if any(part in exclude for part in p.parts):
                continue
            if p.is_file():
                items.append(str(p.relative_to(self._root)))
        return sorted(items)

    def _extract_recent_heresies(self, hive_state: str) -> list[str]:
        """Pull heresy bullet points from the most recent audit block."""
        heresies: list[str] = []
        in_heresies = False
        for line in hive_state.splitlines():
            if "Heresies Detected" in line or "Reflective Insights" in line:
                in_heresies = True
                continue
            if in_heresies:
                stripped = line.strip()
                if stripped.startswith("- "):
                    heresies.append(stripped[2:])
                elif stripped.startswith("**") or stripped.startswith("##"):
                    # New section — stop collecting
                    break
        return heresies[:10]

    async def _fetch_issues(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.settings.github_repository}/issues",
                headers=self._gh_headers(),
                # Omit 'labels' param entirely to return all open issues
                params={"state": "open", "per_page": self.settings.issues_per_page},
            )
            if resp.status_code == 200:
                data: list[dict[str, Any]] = resp.json()
                limit = self.settings.issue_body_limit
                return [
                    {
                        "number": i["number"],
                        "title": i["title"],
                        "body": (i["body"] or "")[:limit],
                    }
                    for i in data
                    if "pull_request" not in i  # exclude PRs from issues endpoint
                ]
        except Exception as e:
            logger.warning("github_issues_fetch_failed", error=str(e))
        return []

    async def _fetch_prs(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.settings.github_repository}/pulls",
                headers=self._gh_headers(),
                params={"state": "open", "per_page": 10},
            )
            if resp.status_code == 200:
                data: list[dict[str, Any]] = resp.json()
                return [
                    {
                        "number": p.get("number"),
                        "title": p.get("title", ""),
                        "head": p.get("head", {}).get("ref", ""),
                    }
                    for p in data
                ]
        except Exception as e:
            logger.warning("github_prs_fetch_failed", error=str(e))
        return []

    def _gh_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
