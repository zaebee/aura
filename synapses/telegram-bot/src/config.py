from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AURA_TELEGRAM__", # Standardized prefix
        env_nested_delimiter="__",
        extra="ignore",
    )

    token: SecretStr = Field(...)
    core_url: str = Field(...)
    nats_url: str = Field(...)
    otel_exporter_otlp_endpoint: str = (
        "http://aura-jaeger.monitoring.svc.cluster.local:4317"
    )
    negotiation_timeout: float = 60.0
    log_level: str = "info"


@lru_cache
def get_settings() -> TelegramSettings:
    return TelegramSettings()  # type: ignore


settings = get_settings()
