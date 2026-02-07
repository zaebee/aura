import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config.crypto import CryptoSettings

from .enzymes.solana import PriceConverter, SecretEncryption, SolanaProvider
from .schema import PaymentProof, PaymentVerificationParams

logger = logging.getLogger(__name__)


class TransactionSkill(
    SkillProtocol[CryptoSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Transaction Protein: Handles payments and encryption.
    Standardized following the Crystalline Protein Standard and Enzyme pattern.
    """

    def __init__(self) -> None:
        self.settings: CryptoSettings | None = None
        self.provider: SolanaProvider | None = None
        self.encryption: SecretEncryption | None = None
        self.converter: PriceConverter | None = None

    def get_name(self) -> str:
        return "transaction"

    def get_capabilities(self) -> list[str]:
        return [
            "verify_payment",
            "encrypt_secret",
            "decrypt_secret",
            "get_address",
            "convert_price",
            "get_network_name",
        ]

    def bind(self, settings: CryptoSettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider.get("provider")
        self.encryption = provider.get("encryption")
        self.converter = provider.get("converter")

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if (
            not self.provider
            or not self.encryption
            or not self.converter
            or not self.settings
        ):
            return Observation(success=False, error="transaction_not_initialized")
        try:
            if intent == "verify_payment":
                p = PaymentVerificationParams(**params)
                proof = await self.provider.verify_payment(p.amount, p.memo, p.currency)
                if proof:
                    return Observation(
                        success=True, data=PaymentProof(**proof).model_dump()
                    )
                return Observation(success=False, error="payment_not_found")

            elif intent == "encrypt_secret":
                encrypted = self.encryption.encrypt(params["secret"])
                return Observation(success=True, data=encrypted)

            elif intent == "decrypt_secret":
                decrypted = self.encryption.decrypt(params["encrypted_secret"])
                return Observation(success=True, data=decrypted)

            elif intent == "convert_price":
                amount = self.converter.convert_usd_to_crypto(
                    params["usd_amount"],
                    params.get("currency", self.settings.currency),
                )
                return Observation(success=True, data=amount)

            elif intent == "get_address":
                return Observation(
                    success=True, data=str(self.provider.keypair.pubkey())
                )

            elif intent == "get_network_name":
                # Return network name from settings (e.g., "solana-mainnet")
                return Observation(
                    success=True, data=self.settings.solana_network or "solana"
                )

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            logger.error(f"Transaction skill error: {e}")
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
