import asyncio
import time
from typing import Any, Optional
import httpx
import structlog

logger = structlog.get_logger(__name__)

class GitHubProvider:
    def __init__(self, token: str, client: httpx.AsyncClient) -> None:
        self.token = token
        self.client = client
        self.base_url = "https://api.github.com"

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        # Inject auth headers
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"token {self.token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        headers["User-Agent"] = "Aura-BeeKeeper"
        kwargs["headers"] = headers

        while True:
            response = await self.client.request(method, url, **kwargs)
            remaining = response.headers.get("X-RateLimit-Remaining")
            if response.status_code == 403 and remaining == "0":
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait_time = max(reset_time - int(time.time()), 1)
                logger.warning("github_rate_limit_hit", wait_time=wait_time, path=path)
                await asyncio.sleep(wait_time)
                continue
            return response

    async def post_comment(self, repo: str, issue_number: Optional[int] = None, commit_sha: Optional[str] = None, body: str = "") -> str:
        if issue_number:
            path = f"repos/{repo}/issues/{issue_number}/comments"
        elif commit_sha:
            path = f"repos/{repo}/commits/{commit_sha}/comments"
        else:
            return ""

        try:
            response = await self._request("POST", path, json={"body": body})
            if response.status_code == 201:
                return str(response.json().get("html_url", ""))

            logger.warning("github_post_comment_failed", status_code=response.status_code, body=response.text)
            return ""
        except Exception as e:
            logger.error("github_post_comment_exception", error=str(e))
            return ""
