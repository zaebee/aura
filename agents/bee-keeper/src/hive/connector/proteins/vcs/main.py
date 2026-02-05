from typing import Any
import httpx
from aura_core import Observation, SkillProtocol
from ._internal import GitHubProvider
from .schema import CommentParams

class VCS_Skill(SkillProtocol[Any, httpx.AsyncClient, dict[str, Any], Observation]):
    """
    VCS Protein: Handles interactions with GitHub.
    Follows the Trinity Pattern (Settings, Provider, Logic).
    """

    def __init__(self) -> None:
        self.settings: Any = None
        self.provider: GitHubProvider | None = None

    def get_name(self) -> str:
        return "vcs"

    def get_capabilities(self) -> list[str]:
        return ["post_comment"]

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

        if intent == "post_comment":
            p = CommentParams(**params)
            url = await self.provider.post_comment(
                repo=p.repo,
                issue_number=p.issue_number,
                commit_sha=p.commit_sha,
                body=p.body
            )
            return Observation(success=bool(url), data={"url": url})

        return Observation(success=False, error=f"Unknown intent: {intent}")
