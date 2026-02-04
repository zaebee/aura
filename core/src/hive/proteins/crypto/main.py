import logging
from typing import Any

from aura_core import Observation, SkillProtocol
from config import get_settings
from config.llm import get_raw_key

from ._solana import CryptoProtein
from ._encryption import SecretEncryption
from ._pricing import PriceConverter

logger = logging.getLogger(__name__)

class CryptoSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Crypto Protein: Handles payments, encryption, and pricing.
    """

    def __init__(self) -> None:
        self.settings = get_settings().crypto
        self.solana = CryptoProtein(
            private_key_base58=get_raw_key(self.settings.solana_private_key),
            rpc_url=str(self.settings.solana_rpc_url),
            network=self.settings.solana_network,
            usdc_mint=self.settings.solana_usdc_mint,
        )
        self.encryption = SecretEncryption(
            get_raw_key(self.settings.secret_encryption_key)
        )
        self.converter = PriceConverter(
            use_fixed_rates=self.settings.use_fixed_rates
        )

    def get_name(self) -> str:
        return "crypto"

    def get_capabilities(self) -> list[str]:
        return [
            "verify_payment",
            "get_address",
            "get_network_name",
            "encrypt_secret",
            "decrypt_secret",
            "convert_price"
        ]

    async def initialize(self) -> bool:
        return await self.solana.initialize()

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "verify_payment":
            return await self.solana.execute("verify_payment", params)
        elif intent == "get_address":
            return await self.solana.execute("get_address", params)
        elif intent == "get_network_name":
            return await self.solana.execute("get_network_name", params)
        elif intent == "encrypt_secret":
            try:
                encrypted = self.encryption.encrypt(params["secret"])
                return Observation(success=True, data=encrypted)
            except Exception as e:
                return Observation(success=False, error=str(e))
        elif intent == "decrypt_secret":
            try:
                decrypted = self.encryption.decrypt(params["encrypted_secret"])
                return Observation(success=True, data=decrypted)
            except Exception as e:
                return Observation(success=False, error=str(e))
        elif intent == "convert_price":
            try:
                amount = self.converter.convert_usd_to_crypto(
                    params["usd_amount"],
                    params.get("currency", self.settings.currency)
                )
                return Observation(success=True, data=amount)
            except Exception as e:
                return Observation(success=False, error=str(e))

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def close(self) -> None:
        await self.solana.close()
