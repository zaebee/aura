import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config.crypto import CryptoSettings

from .engine import PriceConverter, SecretEncryption, SolanaProvider
from .schema import PaymentProof, PaymentVerificationParams

logger = logging.getLogger(__name__)


class TransactionSkill(
    SkillProtocol[CryptoSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Transaction Protein: Handles payments and encryption.
    """

    def __init__(self) -> None:
        self.settings: CryptoSettings | None = None
        self.provider: SolanaProvider | None = None
        self.encryption: SecretEncryption | None = None
        self.converter: PriceConverter | None = None
        self._capabilities = {
            "verify_payment": self._verify_payment,
            "encrypt_secret": self._encrypt_secret,
            "decrypt_secret": self._decrypt_secret,
            "get_address": self._get_address,
            "convert_price": self._convert_price,
            "get_network_name": self._get_network_name,
        }

    def get_name(self) -> str:
        return "transaction"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

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

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Transaction skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _verify_payment(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = PaymentVerificationParams(**params)
        proof = await self.provider.verify_payment(p.amount, p.memo, p.currency)
        if proof:
            return Observation(success=True, data=PaymentProof(**proof).model_dump())
        return Observation(success=False, error="payment_not_found")

    async def _encrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        encrypted = self.encryption.encrypt(params["secret"])
        return Observation(success=True, data=encrypted)

    async def _decrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        decrypted = self.encryption.decrypt(params["encrypted_secret"])
        return Observation(success=True, data=decrypted)

    async def _convert_price(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        amount = self.converter.convert_usd_to_crypto(
            params["usd_amount"],
            params.get("currency", self.settings.currency),
        )
        return Observation(success=True, data=amount)

    async def _get_address(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        return Observation(success=True, data=str(self.provider.keypair.pubkey()))

    async def _get_network_name(self, params: dict[str, Any]) -> Observation:
        assert self.settings is not None
        # Return network name from settings (e.g., "solana-mainnet")
        return Observation(success=True, data=self.settings.solana_network or "solana")

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
