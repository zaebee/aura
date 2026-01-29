from pydantic import BaseModel, HttpUrl, SecretStr, model_validator


class CryptoSettings(BaseModel):
    """Crypto payment configuration for Pay-to-Reveal functionality."""

    # Feature Toggle
    enabled: bool = False  # Set true to enable crypto payment locks

    # Provider Configuration
    provider: str = "solana"  # "solana", "ethereum" (future)
    currency: str = "SOL"  # "SOL", "USDC", "ETH" (future)

    # Solana Configuration
    solana_private_key: SecretStr = ""  # Base58-encoded private key
    solana_rpc_url: HttpUrl = "https://api.devnet.solana.com"
    solana_network: str = "devnet"  # "mainnet-beta", "devnet", "testnet"
    solana_usdc_mint: str = (
        "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"  # Devnet USDC
    )

    # Deal Expiration
    deal_ttl_seconds: int = 3600  # 1 hour default

    # Secret Encryption
    secret_encryption_key: SecretStr = ""  # Base64-encoded Fernet key (32 bytes)

    # Pricing Configuration
    use_fixed_rates: bool = True  # Use fixed rates (not oracle)
    sol_usd_rate: float = 100.0  # Fixed rate: 1 SOL = $100 USD
    # Note: USDC rate is always 1.0 (stablecoin)

    @model_validator(mode="after")
    def validate_crypto_config(self) -> "CryptoSettings":
        """Validate crypto payment configuration when enabled."""
        if self.enabled:
            if not self.solana_private_key:
                raise ValueError(
                    "AURA_CRYPTO__SOLANA_PRIVATE_KEY required when AURA_CRYPTO__ENABLED=true"
                )
            if not self.secret_encryption_key:
                raise ValueError(
                    "AURA_CRYPTO__SECRET_ENCRYPTION_KEY required when AURA_CRYPTO__ENABLED=true. "
                    "See .env.example for key generation instructions."
                )
            if self.currency not in ["SOL", "USDC"]:
                raise ValueError("AURA_CRYPTO__CURRENCY must be 'SOL' or 'USDC'")
            if self.provider not in ["solana"]:
                raise ValueError(
                    "AURA_CRYPTO__PROVIDER must be 'solana' (ethereum support coming soon)"
                )
        return self
