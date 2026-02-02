from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeartbeatSettings(BaseSettings):
    """Settings for the economic heartbeat deal loop (Synthetic Nectar)."""

    model_config = SettingsConfigDict(
        env_prefix="AURA_HEARTBEAT__",
        extra="ignore",
    )

    interval_seconds: int = Field(
        default=12 * 3600,  # Default 12 hours
        description="Interval between heartbeat deals. Set to 60 for testing.",
    )
    bid_multiplier: float = Field(
        default=1.1,
        description="Multiplier applied to base_price for heartbeat bids.",
    )
    agent_did: str = Field(
        default="did:aura:heartbeat",
        description="DID of the synthetic heartbeat agent.",
    )
    agent_reputation: float = Field(
        default=1.0,
        description="Reputation score of the heartbeat agent.",
    )
    enabled: bool = Field(
        default=True,
        description="Enable/disable heartbeat deal loop.",
    )
