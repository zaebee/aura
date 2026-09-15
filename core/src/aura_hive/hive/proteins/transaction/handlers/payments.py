"""Solana payment intents: verify, request, address, network name."""

from typing import Any

from aura_core import make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.crypto import CryptoSettings

from ..schema import PaymentProof, PaymentRequestParams, PaymentVerificationParams
from ..solana_engine import SolanaProvider


class PaymentsHandlers:
    """Payment domain. Owns the provider and read-only settings."""

    capabilities = {
        "verify_payment": "_verify_payment",
        "verify_settlement": "_verify_payment",
        "generate_payment_request": "_generate_payment_request",
        "get_address": "_get_address",
        "get_network_name": "_get_network_name",
    }

    def __init__(
        self, provider: SolanaProvider | None, settings: CryptoSettings | None = None
    ) -> None:
        self.provider = provider
        self.settings = settings

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
