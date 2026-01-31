import asyncio
import json
from typing import Any

import nats
import structlog

from src.config import KeeperSettings
from src.dna import BeeContext, BeeObservation, PurityReport
from src.hive.proteins.gh_client import GitHubClient

logger = structlog.get_logger(__name__)


class BeeConnector:
    """C - Connector: Interacts with GitHub and NATS."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.github_token = settings.github_token
        self.repo_name = settings.github_repository
        self.nats_url = settings.nats_url

        self.gh = None
        if self.github_token and self.github_token != "mock":  # nosec
            self.gh = GitHubClient(self.github_token)

    async def act(self, report: PurityReport, context: BeeContext) -> BeeObservation:
        logger.info("bee_connector_act_started")

        # 1. Post to GitHub (if not a heartbeat)
        comment_url = ""
        injuries = []
        if context.event_name != "schedule":
            comment_url = await self._post_to_github(report, context)
            if not comment_url and self.gh:
                injuries.append("GitHub: Failed to post purity report comment.")

        # 2. Commit Hive State (idempotency handled by Generator writing the file)
        await self._commit_changes()

        # 3. Emit NATS Event
        nats_sent = await self._emit_nats_event(report, context, injuries)

        return BeeObservation(
            success=len(injuries) == 0,
            github_comment_url=comment_url,
            nats_event_sent=nats_sent,
            injuries=injuries
        )

    async def _commit_changes(self) -> None:
        import subprocess  # nosec

        def git_commit() -> None:
            try:
                # Check for changes
                status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    check=False,
                )  # nosec
                if not status.stdout:
                    logger.info("no_changes_to_commit")
                    return

                logger.info("committing_changes", files=status.stdout.splitlines())
                subprocess.run(
                    ["git", "add", "../../HIVE_STATE.md", "../../llms.txt"], check=False
                )  # nosec
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "chore(hive): auto-update hive state [skip ci]",
                    ],
                    check=False,
                )  # nosec
                subprocess.run(["git", "push"], check=False)  # nosec
                logger.info("changes_pushed_successfully")
            except Exception as e:
                logger.warning("git_commit_failed", error=str(e))

        await asyncio.to_thread(git_commit)

    async def _post_to_github(self, report: PurityReport, context: BeeContext) -> str:
        if not self.gh or not self.repo_name:
            logger.warning("github_client_not_initialized_skipping_post")
            return ""

        message = self._format_github_message(report)
        event_data = context.event_data

        pr_num = None
        if "pull_request" in event_data:
            pr_num = event_data["pull_request"].get("number")

        sha = event_data.get("after")
        if not sha and "head_commit" in event_data:
            sha = event_data["head_commit"].get("id")

        # Use the GitHubClient protein
        url = await self.gh.post_comment(
            repo=self.repo_name,
            issue_number=pr_num,
            commit_sha=sha,
            body=message
        )
        return url

    def _format_github_message(self, report: PurityReport) -> str:
        status_emoji = "🍯" if report.is_pure else "⚠️"
        title = "### BeeKeeper Purity Report"

        msg = f"{status_emoji} {title}\n\n"
        msg += f"> {report.narrative}\n\n"

        if report.heresies:
            msg += "**Architectural Heresies Detected:**\n"
            for h in report.heresies:
                msg += f"- {h}\n"
        else:
            msg += "**Architecture is pure. The Hive thrives.**\n"

        if report.reasoning:
            msg += f"\n<details>\n<summary>Keeper's Reasoning</summary>\n\n{report.reasoning}\n</details>"

        return msg

    async def _emit_nats_event(self, report: PurityReport, context: BeeContext, injuries: list[str]) -> bool:
        try:
            nc = await nats.connect(self.nats_url)
            payload = {
                "agent": "bee.Keeper",
                "is_pure": report.is_pure,
                "heresies_count": len(report.heresies),
                "timestamp": asyncio.get_event_loop().time(),
                "injuries": injuries
            }
            await nc.publish("aura.hive.audit", json.dumps(payload).encode())

            if injuries:
                injury_payload = {
                    "agent": "bee.Keeper",
                    "injuries": injuries,
                    "timestamp": asyncio.get_event_loop().time()
                }
                await nc.publish("aura.hive.injury", json.dumps(injury_payload).encode())

            await nc.close()
            return True
        except Exception as e:
            logger.warning("nats_publish_failed", error=str(e))
            return False
