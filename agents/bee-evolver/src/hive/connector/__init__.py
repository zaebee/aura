from typing import Any

import httpx
import structlog

from config import EvolverSettings
from ..models import EvolutionPlan, EvolverObservation, Improvement

logger = structlog.get_logger(__name__)

_GITHUB_API = "https://api.github.com"
_TELEGRAM_API = "https://api.telegram.org"


class EvolverConnector:
    """C - Connector: Opens GitHub Issues/PRs and sends Telegram pulse."""

    def __init__(self, settings: EvolverSettings) -> None:
        self.settings = settings

    async def act(
        self,
        plan: EvolutionPlan,
        branch: str,
        timestamp: str,
        apply_errors: list[str],
    ) -> EvolverObservation:
        logger.info("evolver_connector_act_started")

        issue_urls: list[str] = []
        pr_url = ""
        errors = list(apply_errors)

        async with httpx.AsyncClient(timeout=20.0) as client:
            has_github = (
                self.settings.github_token
                and self.settings.github_token != "mock"  # nosec B105
            )

            if has_github:
                # 1. Create Issues for issue-type improvements
                for imp in plan.improvements:
                    if imp.type == "issue" and imp.issue_body:
                        url = await self._create_issue(client, imp)
                        if url:
                            imp.issue_url = url
                            issue_urls.append(url)

                # 2. Open PR if branch has commits
                if branch:
                    pr_url = await self._open_pr(
                        client, plan, branch, timestamp, issue_urls
                    )

            # 3. Send Telegram pulse (always attempted if configured)
            tg_sent = await self._send_telegram(
                client, plan, pr_url, issue_urls, timestamp, errors
            )

        success = bool(pr_url or plan.hive_is_optimal)
        return EvolverObservation(
            success=success,
            pr_url=pr_url,
            issue_urls=issue_urls,
            branch_name=branch,
            telegram_sent=tg_sent,
            errors=errors,
            plan=plan,
        )

    # ------------------------------------------------------------------
    # GitHub helpers
    # ------------------------------------------------------------------

    async def _create_issue(
        self, client: httpx.AsyncClient, imp: Improvement
    ) -> str:
        try:
            payload: dict[str, Any] = {
                "title": imp.title,
                "body": imp.issue_body or imp.description,
                "labels": ["evolver", "enhancement"],
            }
            if self.settings.evolver_assignee:
                payload["assignees"] = [self.settings.evolver_assignee]

            resp = await client.post(
                f"{_GITHUB_API}/repos/{self.settings.github_repository}/issues",
                headers=self._gh_headers(),
                json=payload,
            )
            if resp.status_code == 201:
                url: str = resp.json().get("html_url", "")
                logger.info("github_issue_created", title=imp.title, url=url)
                return url
            else:
                logger.warning(
                    "github_issue_creation_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
        except Exception as e:
            logger.error("github_issue_error", error=str(e))
        return ""

    async def _open_pr(
        self,
        client: httpx.AsyncClient,
        plan: EvolutionPlan,
        branch: str,
        timestamp: str,
        issue_urls: list[str],
    ) -> str:
        try:
            body = self._build_pr_body(plan, issue_urls)
            payload: dict[str, Any] = {
                "title": f"🧬 Evolver Cycle: {timestamp}",
                "head": branch,
                "base": "main",
                "body": body,
            }
            resp = await client.post(
                f"{_GITHUB_API}/repos/{self.settings.github_repository}/pulls",
                headers=self._gh_headers(),
                json=payload,
            )
            if resp.status_code == 201:
                pr_data = resp.json()
                pr_url: str = pr_data.get("html_url", "")
                pr_number: int = pr_data.get("number", 0)
                logger.info("github_pr_created", url=pr_url)

                # Add labels
                if pr_number:
                    await self._add_pr_labels(client, pr_number)

                return pr_url
            else:
                logger.warning(
                    "github_pr_creation_failed",
                    status=resp.status_code,
                    body=resp.text[:300],
                )
        except Exception as e:
            logger.error("github_pr_error", error=str(e))
        return ""

    async def _add_pr_labels(
        self, client: httpx.AsyncClient, pr_number: int
    ) -> None:
        try:
            await client.post(
                f"{_GITHUB_API}/repos/{self.settings.github_repository}"
                f"/issues/{pr_number}/labels",
                headers=self._gh_headers(),
                json={"labels": ["evolver"]},
            )
        except Exception as e:
            logger.warning("pr_label_failed", error=str(e))

    def _build_pr_body(self, plan: EvolutionPlan, issue_urls: list[str]) -> str:
        lines = [
            "## 🧬 Autonomous Hive Evolution",
            "",
            f"> {plan.narrative}",
            "",
            "### Improvements",
            "",
        ]
        for imp in plan.improvements:
            icon = {"code": "🔧", "prompt": "🧠", "doc": "📄", "issue": "📋"}.get(
                imp.type, "•"
            )
            lines.append(f"**{icon} [{imp.type}] {imp.title}**")
            lines.append(f"{imp.description}")
            if imp.issue_url:
                lines.append(f"→ Issue: {imp.issue_url}")
            lines.append("")

        if issue_urls:
            lines += ["### Related Issues", ""]
            for url in issue_urls:
                lines.append(f"- {url}")
            lines.append("")

        lines += [
            "---",
            "_Generated by bee.Evolver — autonomous Hive improvement agent._",
            "_Review carefully before merging. All commits include `[skip ci]`._",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Telegram helpers
    # ------------------------------------------------------------------

    async def _send_telegram(
        self,
        client: httpx.AsyncClient,
        plan: EvolutionPlan,
        pr_url: str,
        issue_urls: list[str],
        timestamp: str,
        errors: list[str],
    ) -> bool:
        if not self.settings.telegram_token or not self.settings.admin_chat_id:
            logger.warning("telegram_not_configured_skipping")
            return False

        message = self._build_telegram_message(
            plan, pr_url, issue_urls, timestamp, errors
        )
        try:
            resp = await client.post(
                f"{_TELEGRAM_API}/bot{self.settings.telegram_token}/sendMessage",
                json={
                    "chat_id": self.settings.admin_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code == 200:
                logger.info("telegram_pulse_sent", chat_id=self.settings.admin_chat_id)
                return True
            else:
                logger.warning(
                    "telegram_send_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
        except Exception as e:
            logger.error("telegram_error", error=str(e))
        return False

    def _build_telegram_message(
        self,
        plan: EvolutionPlan,
        pr_url: str,
        issue_urls: list[str],
        timestamp: str,
        errors: list[str],
    ) -> str:
        if plan.hive_is_optimal:
            return (
                f"🍯 *bee.Evolver Pulse* — {timestamp}\n"
                "The Hive is crystalline. No mutations required."
            )

        lines = [f"🧬 *bee.Evolver Pulse* — {timestamp}", ""]

        if plan.improvements:
            lines.append(f"*Improvements generated:* {len(plan.improvements)}")
            for imp in plan.improvements:
                icon = {"code": "🔧", "prompt": "🧠", "doc": "📄", "issue": "📋"}.get(
                    imp.type, "•"
                )
                lines.append(f"{icon} {imp.title} `({imp.type})`")
            lines.append("")

        lines.append(f"*Tokens consumed:* {plan.token_usage}")

        if pr_url:
            lines.append(f"*PR:* {pr_url}")

        if errors:
            status = "⚠️ Partial"
        elif plan.improvements:
            status = "✅ Cycle complete"
        else:
            status = "❌ No improvements generated"

        lines.append(f"*Status:* {status}")

        if errors:
            lines.append("")
            lines.append("*Patch errors:*")
            for err in errors[:3]:
                lines.append(f"• {err[:100]}")

        return "\n".join(lines)

    def _gh_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
