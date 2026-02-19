import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

import nats
import nats.errors
import structlog

from config import KeeperSettings
from aura_core import (
    Connector,
    SkillRegistry,
    find_hive_root,
    make_struct,
)
from aura_core_gen.aura.core.v1 import (
    ActionType,
    AuditObservation,
    Context,
    Event,
    NegotiationEvent,
)
from datetime import UTC, datetime
import httpx
from .proteins.vcs import VCS_Skill

logger = structlog.get_logger(__name__)


@dataclass
class BeeObservation:
    """Observation resulting from BeeKeeper's actions."""

    success: bool
    github_comment_url: str = ""
    nats_event_sent: bool = False
    injuries: list[str] = field(default_factory=list)
    report: AuditObservation | None = None
    context: Context | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BeeConnector(Connector[AuditObservation, BeeObservation, Context]):
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

    async def act(self, action: AuditObservation, context: Context) -> BeeObservation:
        # Context here is expected to be Context with BeeData
        return await self.interact(action, context)

    async def interact(
        self, report: AuditObservation, context: Context
    ) -> BeeObservation:
        logger.info("bee_connector_interact_started")

        # 1. Post to Telegram (via NATS Event)
        nats_sent = await self._notify_admin(report, context)

        # 2. Post to GitHub (Legacy, but we keep it if configured)
        comment_url = ""
        injuries: list[str] = []
        if self.gh and self.settings.github_token != "mock":
            comment_url = await self._post_to_github(report, context)

        return BeeObservation(
            success=nats_sent,
            github_comment_url=comment_url,
            nats_event_sent=nats_sent,
            injuries=injuries,
        )

    async def _notify_admin(self, report: AuditObservation, context: Context) -> bool:
        """Emit a NegotiationEvent that the Telegram synapse will pick up."""
        if not self.settings.admin_chat_id:
            logger.warning("admin_chat_id_not_set_skipping_notification")
            return False

        try:
            nc = await nats.connect(self.nats_url, connect_timeout=5.0)
            js = nc.jetstream()

            # We use NegotiationEvent to satisfy the "via NegotiationSignal" (conceptually)
            # but using Event proto so the Effector can pick it up.
            event = Event(
                identifier=f"diag-{uuid.uuid4().hex[:8]}",
                topic="aura.hive.events.negotiation_update",
                timestamp=datetime.now(UTC),
                negotiation=NegotiationEvent(
                    item_identifier="SYSTEM_DIAGNOSIS",
                    action=cast(ActionType, ActionType.ACTION_TYPE_UPDATE),
                    price=0.0,
                ),
                metadata=make_struct({
                    "chat_id": str(self.settings.admin_chat_id),
                    "diagnosis": report.narrative,
                    "fix_suggestion": report.reasoning,
                    "source": "bee-keeper",
                })
            )

            await js.publish(event.topic, bytes(event))
            await nc.close()
            logger.info("admin_notification_sent", chat_id=self.settings.admin_chat_id)
            return True
        except Exception as e:
            logger.error("nats_notification_failed", error=str(e))
            return False

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

    async def _post_to_github(self, report: AuditObservation, context: Context) -> str:
        if not self.gh or not self.repo_name:
            logger.warning("github_client_not_initialized_skipping_post")
            return ""

        message = self._format_github_message(report)
        meta = (
            context.metadata.to_dict() if hasattr(context.metadata, "to_dict") else {}
        )
        event_data = cast(dict[str, Any], meta.get("event_data", {}))

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
        obs_meta = obs.metadata.to_dict() if hasattr(obs.metadata, "to_dict") else {}
        return str(obs_meta.get("url", "")) if obs.success else ""

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

        meta = report.metadata.to_dict() if hasattr(report.metadata, "to_dict") else {}
        reflective_heresies_list: list[str] = cast(
            list[str], meta.get("reflective_heresies", [])
        )
        if reflective_heresies_list:
            msg += "\n**Reflective Insights (The Inquisitor's Eye):**\n"
            for rh in reflective_heresies_list:
                msg += f"- {rh}\n"

        if report.reasoning:
            msg += f"\n<details>\n<summary>Keeper's Reasoning</summary>\n\n{report.reasoning}\n</details>"

        if self.settings.github_cc_recipients:
            msg += f"\n\ncc: {self.settings.github_cc_recipients}"

        return msg

    async def _emit_nats_event(
        self, report: AuditObservation, context: Context, injuries: list[str]
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
