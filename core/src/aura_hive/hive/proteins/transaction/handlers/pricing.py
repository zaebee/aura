"""Pricing intents: tax-and-margin, USD-to-crypto conversion."""

from typing import Any

from aura_core import make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.crypto import CryptoSettings

from ..engine import PriceConverter
from ..schema import TaxCalculationParams


class PricingHandlers:
    """Pricing domain. Owns the converter and read-only settings."""

    capabilities = {
        "calculate_tax_and_margin": "_calculate_tax_and_margin",
        "convert_price": "_convert_price",
    }

    def __init__(
        self, converter: PriceConverter | None, settings: CryptoSettings | None = None
    ) -> None:
        self.converter = converter
        self.settings = settings

    async def _calculate_tax_and_margin(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        p = TaxCalculationParams(**params)
        result = self.converter.calculate_tax_and_margin(
            p.price, margin_rate=self.settings.hive_margin
        )
        return Observation(success=True, metadata=make_struct(result))

    async def _convert_price(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        amount = self.converter.convert_usd_to_crypto(
            params["usd_amount"],
            params.get("currency", self.settings.currency),
        )
        return Observation(success=True, metadata=make_struct({"amount": str(amount)}))
