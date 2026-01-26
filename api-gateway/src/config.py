from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # gRPC Core Service Connection
    core_service_host: str = "localhost:50051"

    # HTTP Server
    http_port: int = 8000

    # OpenTelemetry Configuration
    otel_service_name: str = "aura-gateway"
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"


@lru_cache
def get_settings() -> Settings:
    return Settings()
