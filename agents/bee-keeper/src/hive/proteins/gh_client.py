import asyncio
import time
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

class GitHubClient:
    """Async GitHub client protein for BeeKeeper."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Aura-BeeKeeper",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Internal helper for making async requests with rate limit handling."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.base_url}/{path.lstrip('/')}"
            while True:
                response = await client.request(
                    method, url, headers=self.headers, **kwargs
                )

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
                        path=path
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

    async def post_comment(
        self,
        repo: str,
        issue_number: Optional[int] = None,
        commit_sha: Optional[str] = None,
        body: str = ""
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
