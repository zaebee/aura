from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PerceptionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_PERCEPTION__",
        extra="ignore",
    )

    remote_ollama_url: str = Field("http://aura-frpc-tunnel:11435")
    ollama_url: str = Field("http://localhost:11434")
    model: str = Field("gemma3:latest")
    confidence_threshold: float = Field(0.7)
    ephemeral_asset_ttl: int = Field(3600)
