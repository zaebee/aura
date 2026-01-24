from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://user:pass@db:5432/aura_db"

    # Mistral AI
    mistral_api_key: str

    # gRPC Server
    grpc_port: int = 50051
    grpc_max_workers: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
