
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AURA_TG__",
        extra="ignore",
    )

    token: SecretStr
    core_url: str = "core-service:50051"
    webhook_domain: str | None = None


def get_settings() -> TelegramSettings:
    return TelegramSettings()


settings = get_settings()
