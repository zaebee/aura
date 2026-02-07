from typing import Any

import httpx
from aura_core import Observation, SkillProtocol

from .engine import GitHubProvider
from .schema import CommentParams, ReplyParams


class VCS_Skill(SkillProtocol[Any, httpx.AsyncClient, dict[str, Any], Observation]):
    """
    VCS Protein: Handles interactions with GitHub.
    Follows the Trinity Pattern (Settings, Provider, Logic).
    """

    def __init__(self) -> None:
        self.settings: Any = None
        self.provider: GitHubProvider | None = None
        self._capabilities = {
            "post_comment": self._post_comment,
            "reply_to_comment": self._reply_to_comment,
        }

    def get_name(self) -> str:
        return "vcs"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: Any, provider: httpx.AsyncClient) -> None:
        """
        Bind settings and the shared HTTP client.
        Logic is encapsulated in GitHubProvider.
        """
        self.settings = settings
        token = str(getattr(settings, "github_token", ""))
        self.provider = GitHubProvider(token=token, client=provider)

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _post_comment(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = CommentParams(**params)
        url = await self.provider.post_comment(
            repo=p.repo,
            issue_number=p.issue_number,
            commit_sha=p.commit_sha,
            body=p.body,
        )
        return Observation(success=bool(url), data={"url": url})

    async def _reply_to_comment(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = ReplyParams(**params)
        url = await self.provider.reply_to_comment(
            repo=p.repo,
            pull_number=p.pull_number,
            comment_id=p.comment_id,
            body=p.body,
        )
        return Observation(success=bool(url), data={"url": url})
