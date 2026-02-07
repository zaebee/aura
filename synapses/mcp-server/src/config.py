from pydantic_settings import BaseSettings, SettingsConfigDict

class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_MCP__",
        extra="ignore"
    )
    core_url: str = "localhost:50051"
    log_level: str = "INFO"

settings = MCPSettings()
