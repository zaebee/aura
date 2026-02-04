import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config import get_settings

from ._internal import PriceConverter, SecretEncryption, SolanaProvider
from .schema import PaymentProof, PaymentVerificationParams

logger = logging.getLogger(__name__)


class CryptoSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Crypto Protein: Handles payments and encryption.
    Standardized following the Crystalline Protein Standard.
    """

    def __init__(self) -> None:
        from config.llm import get_raw_key

        self.settings = get_settings()
        self.provider = SolanaProvider(
            private_key_base58=get_raw_key(self.settings.crypto.solana_private_key),
            rpc_url=str(self.settings.crypto.solana_rpc_url),
            usdc_mint=self.settings.crypto.solana_usdc_mint,
        )
        self.encryption = SecretEncryption(
            get_raw_key(self.settings.crypto.secret_encryption_key)
        )
        self.converter = PriceConverter()

    def get_name(self) -> str:
        return "crypto"

    def get_capabilities(self) -> list[str]:
        return ["verify_payment", "encrypt_secret", "decrypt_secret", "get_address"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
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
                encrypted = self.encryption.encrypt(params["text"])
                return Observation(success=True, data={"encrypted": encrypted})

            elif intent == "decrypt_secret":
                decrypted = self.encryption.decrypt(params["encrypted"])
                return Observation(success=True, data={"decrypted": decrypted})

            elif intent == "get_address":
                return Observation(
                    success=True, data={"address": str(self.provider.keypair.pubkey())}
                )

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            logger.error(f"Crypto skill error: {e}")
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        await self.provider.close()
