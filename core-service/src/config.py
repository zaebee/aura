from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "sqlite:///./aura.db"

    # Mistral AI
    mistral_api_key: str = ""

    # gRPC Server
    grpc_port: int = 50051
    grpc_max_workers: int = 10

    # OpenTelemetry Configuration
    otel_service_name: str = "aura-core"
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"

    @model_validator(mode="after")
    def validate_otel_config(self) -> "Settings":
        """Validate OpenTelemetry configuration."""
        if not self.otel_service_name.strip():
            raise ValueError("OTEL_SERVICE_NAME cannot be empty")

        if not self.otel_exporter_otlp_endpoint.startswith(("http://", "https://")):
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be a valid URL")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
