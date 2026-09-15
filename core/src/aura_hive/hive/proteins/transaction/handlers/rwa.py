"""RWA intents: collateral execution (compliance-gated), vault minting."""

from typing import Any

import structlog
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.crypto import CryptoSettings

from ..compliance import enforce_rwa_compliance
from ..schema import RWACollateralParams
from ..solana_engine import SolanaProvider

logger = structlog.get_logger(__name__)


class RWAHandlers:
    """RWA domain. Owns the Solana provider and read-only settings."""

    capabilities = {
        "execute_rwa_collateral": "_execute_rwa_collateral",
        "mint_rwa_vault": "_mint_rwa_vault",
    }

    def __init__(
        self,
        solana_provider: SolanaProvider | None,
        settings: CryptoSettings | None = None,
    ) -> None:
        self.solana_provider = solana_provider
        self.settings = settings

    async def _execute_rwa_collateral(self, params: dict[str, Any]) -> Observation:
        """
        C2C9 Membrane Enforcement: Release SPL Token transfer only if KYC/AML is cleared.
        """
        # 1. Membrane guard: enforce KYC/AML compliance before any motor action.
        required_kyc = (
            self.settings.required_kyc_status if self.settings else "APPROVED"
        )
        required_aml = self.settings.required_aml_risk if self.settings else "LOW"
        enforce_rwa_compliance(params.get("_context"), required_kyc, required_aml)

        # 2. Execution (Motor Neuron action)
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

    async def _mint_rwa_vault(self, params: dict[str, Any]) -> Observation:
        # Stub pending Solana vault program ABI
        return Observation(
            success=False,
            error="mint_rwa_vault_not_implemented_pending_solana_program_abi",
        )
