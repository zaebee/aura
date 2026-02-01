from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AURA_TG__",
        extra="ignore",
    )

    token: SecretStr = Field("")  # type: ignore
    core_url: str = "core-service:50051"
    otel_exporter_otlp_endpoint: str = "http://aura-jaeger.monitoring.svc.cluster.local:4317"
    negotiation_timeout: float = 60.0
    webhook_domain: str | None = None


@lru_cache
def get_settings() -> TelegramSettings:
    return TelegramSettings()  # type: ignore


settings = get_settings()
