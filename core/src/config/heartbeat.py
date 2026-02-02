from pydantic_settings import BaseSettings


class HeartbeatSettings(BaseSettings):
    """Settings for the economic heartbeat deal loop."""

    interval_seconds: int = 12 * 3600  # Default 12 hours
    bid_multiplier: float = 1.1
    agent_did: str = "did:aura:heartbeat"
    agent_reputation: float = 1.0
