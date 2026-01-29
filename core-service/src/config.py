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
    database_url: str = "sqlite:///./aura.db"

    # Mistral AI
    mistral_api_key: str = ""

    # gRPC Server
    grpc_port: int = 50051
    grpc_max_workers: int = 10

    # OpenTelemetry Configuration
    otel_service_name: str = "aura-core"
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"

    # Prometheus Monitoring
    prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.monitoring:9090"

    # LLM Configuration
    llm_model: str = (
        "mistral/mistral-large-latest"  # Default maintains backward compatibility
    )
    # API keys auto-discovered by litellm from environment:
    # - OPENAI_API_KEY (for openai/*)
    # - MISTRAL_API_KEY (for mistral/*)
    # - ANTHROPIC_API_KEY (for anthropic/*)

    # Crypto Payment Configuration
    crypto_enabled: bool = False  # Feature toggle for crypto payments
    crypto_provider: str = "solana"  # "solana", "ethereum" (future)
    crypto_currency: str = "SOL"  # "SOL", "USDC", "ETH" (future)

    # Solana Configuration
    solana_private_key: str = ""  # Base58-encoded private key
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    solana_network: str = "mainnet-beta"  # "mainnet-beta", "devnet", "testnet"
    solana_usdc_mint: str = (
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # Mainnet USDC
    )

    # Deal Expiration
    deal_ttl_seconds: int = 3600  # 1 hour default

    @model_validator(mode="after")
    def validate_otel_config(self) -> "Settings":
        """Validate OpenTelemetry configuration."""
        if not self.otel_service_name.strip():
            raise ValueError("OTEL_SERVICE_NAME cannot be empty")

        if not self.otel_exporter_otlp_endpoint.startswith(("http://", "https://")):
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be a valid URL")

        return self

    @model_validator(mode="after")
    def validate_crypto_config(self) -> "Settings":
        """Validate crypto payment configuration."""
        if self.crypto_enabled:
            if not self.solana_private_key:
                raise ValueError("SOLANA_PRIVATE_KEY required when CRYPTO_ENABLED=true")
            if self.crypto_currency not in ["SOL", "USDC"]:
                raise ValueError("CRYPTO_CURRENCY must be 'SOL' or 'USDC'")
            if self.crypto_provider not in ["solana"]:
                raise ValueError(
                    "CRYPTO_PROVIDER must be 'solana' (ethereum support coming soon)"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
