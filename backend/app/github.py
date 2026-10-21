from urllib.parse import urlparse
import httpx

from .config import Settings
from .schemas import ServiceError


class GitHub:
    def __init__(self, settings: Settings):
        self.settings = settings

    def headers(self):
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": self.settings.github_api_version,
                   "User-Agent": "CloudPulse-Student-Project/1"}
        token = self.settings.github_token.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def check(response: httpx.Response):
        status = response.status_code
        if status in (401, 403):
            limited = response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers
            raise ServiceError("GitHub rate limit reached." if limited else
                               "GitHub rejected access. Check the token, repository selection, and Actions read permission.", limited)
        if status == 404:
            raise ServiceError("GitHub run/log not available. Check permissions; logs may be delayed, deleted, or expired.", True)
        if status == 429 or status >= 500:
            raise ServiceError(f"GitHub temporarily unavailable (HTTP {status}).", True)
        if status >= 400:
            raise ServiceError(f"GitHub request failed (HTTP {status}).")

    async def json(self, path: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.get("https://api.github.com" + path, headers=self.headers())
                self.check(response)
                if response.is_redirect:
                    raise ServiceError("GitHub redirected this repository. Update GITHUB_REPOSITORIES to its current name.")
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError("Could not read GitHub's response. Check network connectivity.", True) from exc

    async def run(self, repository: str, run_id: int, attempt: int | None = None):
        path = f"/repos/{repository}/actions/runs/{run_id}"
        if attempt is not None:
            path += f"/attempts/{attempt}"
        return await self.json(path)

    async def jobs(self, repository: str, run_id: int, attempt: int) -> list[dict]:
        jobs = []
        for page in range(1, 11):
            response = await self.json(f"/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}")
            batch = response.get("jobs", [])
            jobs.extend(batch)
            if len(batch) < 100:
                return jobs
        raise ServiceError("This workflow has too many jobs for the Part 1 limit of 1,000 jobs.")

    async def job_log(self, repository: str, job_id: int) -> tuple[str, bool]:
        """Never forward the GitHub token to the log storage redirect host."""
        url = f"https://api.github.com/repos/{repository}/actions/jobs/{job_id}/logs"
        headers = self.headers()
        try:
            async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
                for _ in range(4):
                    async with client.stream("GET", url, headers=headers) as response:
                        self.check(response)
                        if response.is_redirect:
                            target = response.headers.get("location", "")
                            parsed = urlparse(target)
                            if parsed.scheme != "https" or not parsed.hostname or parsed.username:
                                raise ServiceError("GitHub returned an invalid log download address.")
                            # Target is obtained only from authenticated GitHub/storage responses.
                            url, headers = target, {"User-Agent": "CloudPulse/1"}
                            continue
                        content = bytearray()
                        truncated = False
                        async for chunk in response.aiter_bytes():
                            available = self.settings.max_job_log_bytes - len(content)
                            content.extend(chunk[:max(0, available)])
                            if len(chunk) > available:
                                truncated = True
                                break
                        return content.decode("utf-8", errors="replace"), truncated
                raise ServiceError("Too many redirects while downloading GitHub logs.")
        except httpx.HTTPError as exc:
            raise ServiceError("GitHub log download timed out or lost connectivity.", True) from exc
