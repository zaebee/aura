import asyncio
import json


import nats
import nats.errors
import structlog

from config import KeeperSettings
from aura_core import (
    AuditObservation,
    BeeContext,
    BeeObservation,
    Connector,
    SkillRegistry,
    find_hive_root,
)
import httpx
from .proteins.vcs import VCS_Skill

logger = structlog.get_logger(__name__)


class BeeConnector(Connector[AuditObservation, BeeObservation, BeeContext]):
    """C - Connector: Interacts with GitHub and NATS."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.registry = SkillRegistry()
        self.settings = settings
        self.github_token = settings.github_token
        self.repo_name = settings.github_repository
        self.nats_url = settings.nats_url
        self._http_client = httpx.AsyncClient(timeout=30.0)

        self.gh = None
        if self.github_token and self.github_token != "mock":  # nosec
            self.gh = VCS_Skill()
            self.gh.bind(settings, self._http_client)

    async def close(self) -> None:
        """Cleanup resources."""
        await self._http_client.aclose()

    async def act(
        self, action: AuditObservation, context: BeeContext
    ) -> BeeObservation:
        # Context here is expected to be BeeContext
        return await self.interact(action, context)

    async def interact(
        self, report: AuditObservation, context: BeeContext
    ) -> BeeObservation:
        logger.info("bee_connector_interact_started")

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
            injuries=injuries,
        )

    async def _commit_changes(self) -> None:
        import subprocess  # nosec

        root = find_hive_root()

        def git_commit() -> None:
            try:
                # Check for changes
                status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(root),
                )  # nosec
                if not status.stdout:
                    logger.info("no_changes_to_commit")
                    return

                logger.info("committing_changes", files=status.stdout.splitlines())
                subprocess.run(
                    ["git", "add", "HIVE_STATE.md", "llms.txt"],
                    check=False,
                    cwd=str(root),
                )  # nosec
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        "chore(hive): auto-update hive state [skip ci]",
                    ],
                    check=False,
                    cwd=str(root),
                )  # nosec
                subprocess.run(["git", "push"], check=False, cwd=str(root))  # nosec
                logger.info("changes_pushed_successfully")
            except Exception as e:
                logger.warning("git_commit_failed", error=str(e))

        await asyncio.to_thread(git_commit)

    async def _post_to_github(
        self, report: AuditObservation, context: BeeContext
    ) -> str:
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
        obs = await self.gh.execute(
            "post_comment",
            {
                "repo": self.repo_name,
                "issue_number": pr_num,
                "commit_sha": sha,
                "body": message,
            },
        )
        return obs.data.get("url", "") if obs.success else ""

    def _format_github_message(self, report: AuditObservation) -> str:
        status_emoji = "🍯" if report.is_pure else "⚠️"
        title = "### BeeKeeper Audit Observation"

        msg = f"{status_emoji} {title}\n\n"
        msg += f"> {report.narrative}\n\n"

        if report.heresies:
            msg += "**Architectural Heresies Detected:**\n"
            for h in report.heresies:
                msg += f"- {h}\n"
        else:
            msg += "**The Hive's structure is sanctified.**\n"

        reflective_heresies = report.metadata.get("reflective_heresies", [])
        if reflective_heresies:
            msg += "\n**Reflective Insights (The Inquisitor's Eye):**\n"
            for rh in reflective_heresies:
                msg += f"- {rh}\n"

        if report.reasoning:
            msg += f"\n<details>\n<summary>Keeper's Reasoning</summary>\n\n{report.reasoning}\n</details>"

        if self.settings.github_cc_recipients:
            msg += f"\n\ncc: {self.settings.github_cc_recipients}"

        return msg

    async def _emit_nats_event(
        self, report: AuditObservation, context: BeeContext, injuries: list[str]
    ) -> bool:
        try:
            # Use connect_timeout to prevent hanging if NATS is unreachable
            nc = await nats.connect(self.nats_url, connect_timeout=5.0)
            now = asyncio.get_running_loop().time()
            payload = {
                "agent": "bee.Keeper",
                "is_pure": report.is_pure,
                "heresies_count": len(report.heresies),
                "timestamp": now,
                "injuries": injuries,
            }
            await nc.publish("aura.hive.audit", json.dumps(payload).encode())

            if injuries:
                injury_payload = {
                    "agent": "bee.Keeper",
                    "injuries": injuries,
                    "timestamp": now,
                }
                await nc.publish(
                    "aura.hive.injury", json.dumps(injury_payload).encode()
                )

            await nc.close()
            return True
        except (nats.errors.NoServersError, nats.errors.TimeoutError, Exception) as e:
            # Log warning and return False to allow metabolic cycle to complete.
            # We avoid logging the URL to prevent potential credential leakage.
            logger.warning("nats_connection_failed", error=str(e))
            return False
