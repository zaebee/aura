from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .crypto import CryptoSettings
from .database import DatabaseSettings
from .llm import LLMSettings
from .logic import LogicSettings
from .server import ServerSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="AURA_",
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    crypto: CryptoSettings = Field(default_factory=CryptoSettings)
    logic: LogicSettings = Field(default_factory=LogicSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
