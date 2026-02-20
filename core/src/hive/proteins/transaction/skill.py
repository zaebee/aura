from typing import Any

import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation

from config.crypto import CryptoSettings

from .engine import PriceConverter, SecretEncryption
from .schema import (
    PaymentProof,
    PaymentRequestParams,
    PaymentVerificationParams,
    TaxCalculationParams,
)

logger = structlog.get_logger(__name__)


class TransactionSkill(
    SkillProtocol[CryptoSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Transaction Protein: Handles payments and encryption.
    """

    def __init__(self) -> None:
        self.settings: CryptoSettings | None = None
        self.provider: Any = None
        self.solana_provider: Any = None
        self.evm_provider: Any = None
        self.encryption: SecretEncryption | None = None
        self.converter: PriceConverter | None = None
        self._capabilities = {
            "verify_payment": self._verify_payment,
            "verify_settlement": self._verify_payment,
            "generate_payment_request": self._generate_payment_request,
            "calculate_tax_and_margin": self._calculate_tax_and_margin,
            "encrypt_secret": self._encrypt_secret,
            "decrypt_secret": self._decrypt_secret,
            "get_address": self._get_address,
            "convert_price": self._convert_price,
            "get_network_name": self._get_network_name,
            "transfer": self._transfer,
        }

    def get_name(self) -> str:
        return "transaction"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: CryptoSettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider.get("provider")
        self.solana_provider = provider.get("solana_provider")
        self.evm_provider = provider.get("evm_provider")
        self.encryption = provider.get("encryption")
        self.converter = provider.get("converter")

    async def initialize(self) -> bool:
        if self.settings and self.settings.wallet_address and self.provider:
            derived_addr = str(self.provider.keypair.pubkey())
            if derived_addr != self.settings.wallet_address:
                logger.error(
                    "wallet_address_mismatch",
                    expected=self.settings.wallet_address,
                    derived=derived_addr,
                )
                return False
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
            return Observation(
                success=True,
                metadata=make_struct(PaymentProof(**proof).model_dump()),
            )
        return Observation(success=False, error="payment_not_found")

    async def _generate_payment_request(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = PaymentRequestParams(**params)
        uri = self.provider.generate_payment_request(
            p.amount, p.memo, p.currency, p.label, p.message
        )
        return Observation(success=True, metadata=make_struct({"uri": str(uri)}))

    async def _calculate_tax_and_margin(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        p = TaxCalculationParams(**params)
        result = self.converter.calculate_tax_and_margin(
            p.price, margin_rate=self.settings.hive_margin
        )
        return Observation(success=True, metadata=make_struct(result))

    async def _encrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        encrypted = self.encryption.encrypt(params["secret"])
        return Observation(
            success=True,
            metadata=make_struct({"encrypted_secret": str(encrypted)}),
        )

    async def _decrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        decrypted = self.encryption.decrypt(params["encrypted_secret"])
        return Observation(
            success=True,
            metadata=make_struct({"decrypted_secret": str(decrypted)}),
        )

    async def _convert_price(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        amount = self.converter.convert_usd_to_crypto(
            params["usd_amount"],
            params.get("currency", self.settings.currency),
        )
        return Observation(success=True, metadata=make_struct({"amount": str(amount)}))

    async def _get_address(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        return Observation(
            success=True,
            metadata=make_struct({"address": str(self.provider.keypair.pubkey())}),
        )

    async def _get_network_name(self, params: dict[str, Any]) -> Observation:
        assert self.settings is not None
        # Return network name from settings (e.g., "solana-mainnet")
        return Observation(
            success=True,
            metadata=make_struct(
                {"network": str(self.settings.solana_network or "solana")}
            ),
        )

    async def _transfer(self, params: dict[str, Any]) -> Observation:
        network = params.get("network", "base-sepolia")
        amount = float(params["amount"])
        recipient = params["recipient"]

        try:
            if network in ["base-sepolia", "evm"]:
                if not self.evm_provider:
                    return Observation(
                        success=False, error="evm_provider_not_initialized"
                    )
                tx_hash = await self.evm_provider.transfer_usdc(recipient, amount)
                return Observation(
                    success=True,
                    metadata=make_struct({"transaction_hash": tx_hash}),
                )
            else:
                return Observation(
                    success=False, error=f"Transfer not implemented for {network}"
                )
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
