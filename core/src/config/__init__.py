from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .blockchain_data import BlockchainDataSettings
from .crypto import CryptoSettings
from .database import DatabaseSettings
from .discovery import DiscoverySettings
from .heartbeat import HeartbeatSettings
from .kinetic import KineticSettings
from .llm import LLMSettings
from .logic import LogicSettings
from .perception import PerceptionSettings
from .policy import SafetySettings
from .server import ServerSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="AURA_",
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings())  # type: ignore
    llm: LLMSettings = Field(default_factory=lambda: LLMSettings())  # type: ignore
    crypto: CryptoSettings = Field(default_factory=lambda: CryptoSettings())  # type: ignore
    logic: LogicSettings = Field(default_factory=lambda: LogicSettings())  # type: ignore
    safety: SafetySettings = Field(default_factory=lambda: SafetySettings())  # type: ignore
    server: ServerSettings = Field(default_factory=lambda: ServerSettings())  # type: ignore
    heartbeat: HeartbeatSettings = Field(default_factory=lambda: HeartbeatSettings())  # type: ignore
    perception: PerceptionSettings = Field(default_factory=lambda: PerceptionSettings())  # type: ignore
    kinetic: KineticSettings = Field(default_factory=lambda: KineticSettings())  # type: ignore
    discovery: DiscoverySettings = Field(default_factory=lambda: DiscoverySettings())  # type: ignore
    blockchain_data: BlockchainDataSettings = Field(
        default_factory=lambda: BlockchainDataSettings()
    )  # type: ignore


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
