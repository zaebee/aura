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
