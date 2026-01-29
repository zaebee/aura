from typing import Optional
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="AURA_TELEGRAM__",
        extra="ignore",
    )

    bot_token: SecretStr
    core_grpc_url: str = "core-service:50051"
    webhook_url: Optional[HttpUrl] = None
    use_polling: bool = True


def get_settings() -> TelegramSettings:
    return TelegramSettings()


settings = get_settings()
