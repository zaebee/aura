from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_MCP__",
        env_nested_delimiter="__",
        extra="ignore",
    )
    gateway_url: str = "http://localhost:8000"
    core_url: str = "localhost:50051"
    log_level: str = "INFO"
    nats_url: str = "nats://localhost:4222"

settings = MCPSettings()
