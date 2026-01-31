from functools import lru_cache

from pydantic import HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # gRPC Core Service Connection
    core_service_host: str = "localhost:50051"
    negotiation_timeout: float = 30.0

    # HTTP Server
    http_port: int = 8000

    # OpenTelemetry Configuration
    otel_service_name: str = "aura-gateway"
    otel_exporter_otlp_endpoint: HttpUrl = "http://jaeger:4317"  # type: ignore

    # CORS Configuration
    # Comma-separated list of allowed origins (e.g., "https://app1.com,https://app2.com")
    # Defaults to production URL, can be overridden for development
    cors_origins: str = "https://aura.zae.life"

    # Health Check Configuration
    health_check_timeout: float = (
        0.5  # Timeout for core service health checks (seconds)
    )
    health_check_slow_threshold_ms: float = (
        100.0  # Log warning if health check exceeds this duration (milliseconds)
    )

    @model_validator(mode="after")
    def validate_otel_config(self) -> "Settings":
        """Validate OpenTelemetry configuration."""
        if not self.otel_service_name.strip():
            raise ValueError("OTEL_SERVICE_NAME cannot be empty")

        if not str(self.otel_exporter_otlp_endpoint).startswith(("http://", "https://")):
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be a valid URL")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
