"""Settings for the economic heartbeat deal loop."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeartbeatSettings(BaseSettings):
    """Settings for the economic heartbeat deal loop."""

    model_config = SettingsConfigDict(
        env_prefix="AURA_HEARTBEAT__",
        extra="ignore",
    )

    interval_seconds: int = Field(
        default=60,  # Default 60 seconds for health visibility
        description="Interval in seconds between heartbeat deals for system health visibility.",
    )
    bid_multiplier: float = Field(
        default=1.2,
        description="Multiplier applied to base_price for heartbeat bids. Must exceed (1/(1-min_margin)) for acceptance.",
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
