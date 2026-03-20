from typing import Any

import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation
from hive.metabolism import MetabolicSecurityError

from config.crypto import CryptoSettings

from .engine import PriceConverter, SecretEncryption
from .schema import (
    PaymentProof,
    PaymentRequestParams,
    PaymentVerificationParams,
    RWACollateralParams,
    TaxCalculationParams,
    TradeIntentParams,
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
            "sign_trade_intent": self._sign_trade_intent,
            "submit_to_router": self._submit_to_router,
            "execute_rwa_collateral": self._execute_rwa_collateral,
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
        except MetabolicSecurityError:
            raise
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

    async def _sign_trade_intent(self, params: dict[str, Any]) -> Observation:
        if not self.evm_provider:
            return Observation(success=False, error="evm_provider_not_initialized")

        trade_intent_dict = params.get("intent")
        if not trade_intent_dict:
            return Observation(success=False, error="intent_params_missing")

        try:
            # Validate input using Pydantic schema
            p = TradeIntentParams(**trade_intent_dict)
            result = await self.evm_provider.sign_eip712_trade_intent(p.model_dump())
            return Observation(
                success=True,
                metadata=make_struct(result),
            )
        except Exception as e:
            logger.error(f"EIP-712 signing failed: {e}")
            return Observation(success=False, error=str(e))

    async def _submit_to_router(self, params: dict[str, Any]) -> Observation:
        # Stub for March 9th release
        return Observation(
            success=False,
            error="submit_to_router_not_implemented_pending_abi",
        )

    async def _execute_rwa_collateral(self, params: dict[str, Any]) -> Observation:
        """
        C2C9 Membrane Enforcement: Release SPL Token transfer only if KYC/AML is cleared.
        """
        # 1. Access context metadata for security enforcement
        context = params.get("_context")
        if not context:
            raise MetabolicSecurityError("Security context missing: HiveContext required")

        # Extract metadata from Context (google.protobuf.Struct)
        metadata = context.metadata.to_dict() if hasattr(context.metadata, "to_dict") else {}
        kyc_status = metadata.get("kyc_status")
        aml_risk = metadata.get("aml_risk")

        # 2. Strict C2C9 Enforcement logic
        if kyc_status != "APPROVED" or aml_risk != "LOW":
            logger.error(
                "c2c9_security_violation",
                kyc_status=kyc_status,
                aml_risk=aml_risk,
                agent_did=metadata.get("agent_did", "unknown"),
            )
            raise MetabolicSecurityError(
                f"C2C9 Membrane Violation: Compliance failure (KYC: {kyc_status}, AML: {aml_risk})"
            )

        # 3. Execution (Motor Neuron action)
        if not self.solana_provider:
            return Observation(success=False, error="solana_provider_not_initialized")

        p = RWACollateralParams(**params)
        try:
            tx_hash = await self.solana_provider.execute_rwa_collateral(
                p.wallet_address, p.amount_usdc
            )
            return Observation(
                success=True,
                metadata=make_struct({"transaction_hash": tx_hash}),
            )
        except Exception as e:
            logger.error(f"RWA Collateral execution failed: {e}")
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
