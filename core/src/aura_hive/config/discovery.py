from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DiscoverySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_DISCOVERY__",
        extra="ignore",
        populate_by_name=True,
    )

    github_token: SecretStr = Field(
        SecretStr(""),
        validation_alias=AliasChoices("AURA_DISCOVERY__GITHUB_TOKEN", "GITHUB_TOKEN"),
    )
    scan_repo_limit: int = Field(
        5, description="Maximum number of repositories to scan."
    )
    proposal_compatibility_threshold: float = Field(
        0.7, description="Minimum compatibility score to generate a symbiotic proposal."
    )
