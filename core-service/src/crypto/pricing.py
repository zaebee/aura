"""
Currency conversion for crypto payments.
Converts fiat (USD) prices to cryptocurrency amounts.
"""
import logging
from decimal import Decimal
from typing import Literal

logger = logging.getLogger(__name__)

CryptoCurrency = Literal["SOL", "USDC"]


class PriceConverter:
    """
    Converts fiat prices to cryptocurrency amounts.

    Uses fixed exchange rates for deterministic pricing.
    Production: Replace with oracle integration (Pyth, Chainlink).
    """

    # Fixed exchange rates (USD per 1 crypto unit)
    # TODO: Replace with oracle in production
    FIXED_RATES = {
        "SOL": Decimal("100.0"),   # 1 SOL = $100 USD
        "USDC": Decimal("1.0"),    # 1 USDC = $1 USD (stablecoin)
    }

    def __init__(self, use_fixed_rates: bool = True):
        """
        Initialize price converter.

        Args:
            use_fixed_rates: Use fixed rates (True) or oracle (False)
        """
        self.use_fixed_rates = use_fixed_rates
        if not use_fixed_rates:
            raise NotImplementedError("Oracle integration not yet implemented")

    def convert_usd_to_crypto(
        self,
        usd_amount: float,
        crypto_currency: CryptoCurrency
    ) -> float:
        """
        Convert USD amount to cryptocurrency amount.

        Args:
            usd_amount: Amount in USD (e.g., 150.0)
            crypto_currency: Target currency ("SOL" or "USDC")

        Returns:
            Amount in cryptocurrency (e.g., 1.5 SOL for $150 at $100/SOL)

        Example:
            >>> converter = PriceConverter()
            >>> converter.convert_usd_to_crypto(150.0, "SOL")
            1.5  # 150 USD / 100 USD per SOL
        """
        if crypto_currency not in self.FIXED_RATES:
            raise ValueError(f"Unsupported currency: {crypto_currency}")

        usd_decimal = Decimal(str(usd_amount))
        rate = self.FIXED_RATES[crypto_currency]
        crypto_amount = usd_decimal / rate

        logger.info(
            "currency_conversion",
            extra={
                "usd_amount": usd_amount,
                "crypto_currency": crypto_currency,
                "rate": float(rate),
                "crypto_amount": float(crypto_amount),
            }
        )

        return float(crypto_amount)
