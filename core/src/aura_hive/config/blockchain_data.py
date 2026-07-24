from pydantic import BaseModel, HttpUrl


class BlockchainDataSettings(BaseModel):
    """Configuration for GoldRush x402 data foraging."""

    base_url: HttpUrl = "https://x402.goldrush.dev/v1"  # type: ignore
    discovery_url: HttpUrl = "https://goldrush.dev/llms.txt"  # type: ignore
