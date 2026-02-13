from typing import Any

import betterproto
import structlog
from aura_core import Observation, SkillProtocol
from aura_core.gen.aura.core.v1 import (
    PaymentProof,
)
from aura_core.gen.aura.core.v1.google import protobuf

from config.crypto import CryptoSettings

from .engine import PriceConverter, SecretEncryption, SolanaProvider
from .schema import (
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
        self.provider: SolanaProvider | None = None
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

    def _pack_payload(self, message: betterproto.Message) -> protobuf.Any:
        any_payload = protobuf.Any()
        any_payload.value = bytes(message)
        # Type URL is optional for internal bloodstream but good practice
        # any_payload.type_url = f"type.googleapis.com/{message.__class__.__module__}.{message.__class__.__name__}"
        return any_payload

    async def _verify_payment(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = PaymentVerificationParams(**params)
        proof_dict = await self.provider.verify_payment(p.amount, p.memo, p.currency)
        if proof_dict:
            # proof_dict contains keys like 'transaction_hash', etc.
            proof = PaymentProof(
                transaction_hash=proof_dict.get("transaction_hash", ""),
                block_number=str(proof_dict.get("block_number", "")),
                from_address=proof_dict.get("from_address", "")
            )
            return Observation(
                success=True,
                payload=self._pack_payload(proof)
            )
        return Observation(success=False, error="payment_not_found")

    async def _generate_payment_request(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = PaymentRequestParams(**params)
        uri = self.provider.generate_payment_request(
            p.amount, p.memo, p.currency, p.label, p.message
        )
        val = protobuf.StringValue(value=uri)
        return Observation(success=True, payload=self._pack_payload(val))

    async def _calculate_tax_and_margin(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        p = TaxCalculationParams(**params)
        result = self.converter.calculate_tax_and_margin(
            p.price, margin_rate=self.settings.hive_margin
        )
        # result is {'margin': 10.0, 'total': 110.0}
        # Pack as metadata for now since it's primitives, or just use a custom message if we had one.
        # Let's use metadata for these simple floats to avoid creating too many protos.
        return Observation(
            success=True,
            metadata={
                "margin": str(result["margin"]),
                "total": str(result["total"])
            }
        )

    async def _encrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        encrypted = self.encryption.encrypt(params["secret"])
        val = protobuf.StringValue(value=encrypted)
        return Observation(success=True, payload=self._pack_payload(val))

    async def _decrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        decrypted = self.encryption.decrypt(params["encrypted_secret"])
        val = protobuf.StringValue(value=decrypted)
        return Observation(success=True, payload=self._pack_payload(val))

    async def _convert_price(self, params: dict[str, Any]) -> Observation:
        assert self.converter is not None
        assert self.settings is not None
        amount = self.converter.convert_usd_to_crypto(
            params["usd_amount"],
            params.get("currency", self.settings.currency),
        )
        val = protobuf.DoubleValue(value=amount)
        return Observation(success=True, payload=self._pack_payload(val))

    async def _get_address(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        val = protobuf.StringValue(value=str(self.provider.keypair.pubkey()))
        return Observation(success=True, payload=self._pack_payload(val))

    async def _get_network_name(self, params: dict[str, Any]) -> Observation:
        assert self.settings is not None
        # Return network name from settings (e.g., "solana-mainnet")
        val = protobuf.StringValue(value=self.settings.solana_network or "solana")
        return Observation(success=True, payload=self._pack_payload(val))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
