import asyncio
import time
from typing import Any, Optional

import httpx
import structlog
from aura_core import Observation, Skill

logger = structlog.get_logger(__name__)


class GitHubClient(Skill):
    """Async GitHub client protein for BeeKeeper."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Aura-BeeKeeper",
        }
        self._client = httpx.AsyncClient(timeout=30.0, headers=self.headers)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Internal helper for making async requests with rate limit handling."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        while True:
            response = await self._client.request(method, url, **kwargs)

            # Handle rate limiting (Metabolic slowing)
            remaining = response.headers.get("X-RateLimit-Remaining")
            if response.status_code == 403 and remaining == "0":
                reset_time = int(
                    response.headers.get("X-RateLimit-Reset", time.time() + 60)
                )
                wait_time = max(reset_time - int(time.time()), 1)
                logger.warning(
                    "github_rate_limit_hit_metabolic_slowing",
                    wait_time=wait_time,
                    path=path,
                )
                await asyncio.sleep(wait_time)
                continue

            if response.status_code >= 400:
                logger.error(
                    "github_api_error",
                    status_code=response.status_code,
                    path=path,
                    # No logging of headers or sensitive repository metadata beyond the path
                )

            return response

    def get_name(self) -> str:
        return "github-client"

    def get_capabilities(self) -> list[str]:
        return ["post_comment"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "post_comment":
            url = await self.post_comment(
                repo=params["repo"],
                issue_number=params.get("issue_number"),
                commit_sha=params.get("commit_sha"),
                body=params.get("body", ""),
            )
            return Observation(success=bool(url), data={"url": url})
        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def post_comment(
        self,
        repo: str,
        issue_number: Optional[int] = None,
        commit_sha: Optional[str] = None,
        body: str = "",
    ) -> str:
        """
        Post a comment to a PR (issue) or a specific commit.
        Returns the HTML URL of the comment if successful, else an empty string.
        """
        if issue_number:
            path = f"repos/{repo}/issues/{issue_number}/comments"
        elif commit_sha:
            path = f"repos/{repo}/commits/{commit_sha}/comments"
        else:
            logger.error("github_post_comment_missing_target")
            return ""

        try:
            response = await self._request("POST", path, json={"body": body})

            if response.status_code == 201:
                url = str(response.json().get("html_url", ""))
                logger.info("github_comment_posted", url=url)
                return url
            else:
                # Handle 403/404 specifically for reporting
                error_msg = f"GitHub API error {response.status_code} on {path}"
                logger.warning("github_post_comment_failed", error=error_msg)
                return ""
        except Exception as e:
            logger.error("github_client_request_exception", error=str(e))
            return ""
