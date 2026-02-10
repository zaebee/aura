from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PerceptionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_PERCEPTION__",
        extra="ignore",
    )

    ollama_url: str = Field("http://localhost:11434")
    model: str = Field("gemma3:latest")
