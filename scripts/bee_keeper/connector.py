import asyncio
import json
import os
from typing import Any

import nats
import structlog
from github import Github

from src.hive.dna import BeeContext, BeeObservation, PurityReport

logger = structlog.get_logger(__name__)

class BeeConnector:
    """C - Connector: Interacts with GitHub and NATS."""

    def __init__(self) -> None:
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo_name = os.getenv("GITHUB_REPOSITORY")
        self.nats_url = os.getenv("NATS_URL", "nats://nats:4222")

        self.gh = None
        if self.github_token and self.github_token != "mock":  # nosec
            self.gh = Github(self.github_token)

    async def act(self, report: PurityReport, context: BeeContext) -> BeeObservation:
        logger.info("bee_connector_act_started")

        # 1. Post to GitHub
        comment_url = await self._post_to_github(report, context)

        # 2. Emit NATS Event
        nats_sent = await self._emit_nats_event(report, context)

        return BeeObservation(
            success=True,
            github_comment_url=comment_url,
            nats_event_sent=nats_sent
        )

    async def _post_to_github(self, report: PurityReport, context: BeeContext) -> str:
        if not self.gh or not self.repo_name:
            logger.warning("github_client_not_initialized_skipping_post")
            return ""

        # Capture repo_name and gh for the closure
        repo_name: str = self.repo_name
        gh = self.gh

        def post() -> str:
            try:
                repo = gh.get_repo(repo_name)
                message = self._format_github_message(report)

                event_data = context.event_data
                if "pull_request" in event_data:
                    pr_num = event_data["pull_request"]["number"]
                    comment: Any = repo.get_pull(pr_num).create_issue_comment(message)
                    return str(comment.html_url)
                else:
                    sha = event_data.get("after")
                    if not sha and "head_commit" in event_data:
                        sha = event_data["head_commit"].get("id")

                    if sha:
                        comment = repo.get_commit(sha).create_comment(message)
                        return str(comment.html_url)

                # Fallback
                branch = repo.get_branch("main")
                comment = branch.commit.create_comment(message)
                return str(comment.html_url)
            except Exception as e:
                logger.error("github_post_failed", error=str(e))
                return ""

        return await asyncio.to_thread(post)

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

    async def _emit_nats_event(self, report: PurityReport, context: BeeContext) -> bool:
        try:
            nc = await nats.connect(self.nats_url)
            payload = {
                "agent": "bee.Keeper",
                "is_pure": report.is_pure,
                "heresies_count": len(report.heresies),
                "timestamp": asyncio.get_event_loop().time()
            }
            await nc.publish("aura.hive.audit", json.dumps(payload).encode())
            await nc.close()
            return True
        except Exception as e:
            logger.warning("nats_publish_failed", error=str(e))
            return False
