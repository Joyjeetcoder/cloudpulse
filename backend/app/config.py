from pathlib import Path
import re

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    github_token: SecretStr = SecretStr("")
    github_webhook_secret: SecretStr
    dashboard_token: SecretStr
    github_repositories: str
    github_api_version: str = "2022-11-28"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    gemini_max_output_tokens: int = Field(4096, ge=512, le=8192)
    gemini_timeout_seconds: int = Field(90, ge=10, le=180)
    max_excerpt_chars: int = Field(14000, ge=2000, le=30000)
    max_failed_jobs: int = Field(5, ge=1, le=10)
    max_job_log_bytes: int = Field(5_000_000, ge=10000, le=20_000_000)
    max_analysis_attempts: int = Field(3, ge=1, le=5)
    data_dir: Path = Path("./data")
    frontend_dir: Path = Path("./static")

    @field_validator("github_webhook_secret", "dashboard_token")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 32 or "replace" in raw.lower() or "change-me" in raw.lower():
            raise ValueError("Generate a unique random secret of at least 32 characters.")
        return value

    @field_validator("gemini_model")
    @classmethod
    def model_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError("Use a Gemini model ID without a models/ prefix.")
        return value

    @field_validator("github_repositories")
    @classmethod
    def repositories(cls, value: str) -> str:
        repos = [r.strip().lower() for r in value.split(",") if r.strip()]
        if not repos or any(not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", r) for r in repos):
            raise ValueError("GITHUB_REPOSITORIES must contain owner/repo names, separated by commas.")
        return ",".join(repos)

    @model_validator(mode="after")
    def different_secrets(self):
        if self.github_webhook_secret == self.dashboard_token:
            raise ValueError("Use different webhook and dashboard secrets.")
        return self

    @property
    def repositories_set(self) -> set[str]:
        return set(self.github_repositories.split(","))

    @property
    def known_secrets(self) -> list[str]:
        return [s.get_secret_value() for s in (
            self.github_token, self.github_webhook_secret, self.dashboard_token,
            self.gemini_api_key,
        ) if s.get_secret_value()]
