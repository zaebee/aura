from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AURA_TELEGRAM__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    token: SecretStr = Field(default=SecretStr("placeholder"))  # type: ignore
    nats_url: str = Field(default="nats://localhost:4222")  # type: ignore
    core_grpc_url: str = Field("localhost:50051")
    signal_subject: str = "aura.synapse.telegram.signal"
    otel_exporter_otlp_endpoint: str = (
        "http://aura-jaeger.monitoring.svc.cluster.local:4317"
    )
    negotiation_timeout: float = 60.0
    webhook_domain: str | None = None
    health_port: int = 8080
    search_limit: int = 10
    default_item_domain: str = "hotel"
    log_level: str = "info"
    debug: bool = False


@lru_cache
def get_settings() -> TelegramSettings:
    return TelegramSettings()  # type: ignore


settings = get_settings()
