import logging
from typing import Any

from aura_core import Observation, SkillProtocol
from ._solana import SolanaProvider

logger = logging.getLogger(__name__)

class CryptoSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Solana blockchain payment verification provider.
    """

    def __init__(
        self,
        private_key_base58: str,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        network: str = "mainnet-beta",
        usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    ) -> None:
        self.provider = SolanaProvider(
            private_key_base58=private_key_base58,
            rpc_url=rpc_url,
            network=network,
            usdc_mint=usdc_mint
        )

    def get_name(self) -> str:
        return "crypto"

    def get_capabilities(self) -> list[str]:
        return ["verify_payment", "get_address", "get_network_name"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        match intent:
            case "verify_payment":
                proof = await self.provider.verify_payment(
                    amount=params.get("amount", 0.0),
                    memo=params.get("memo", ""),
                    currency=params.get("currency", "SOL"),
                )
                if proof:
                    return Observation(success=True, data=proof)
                return Observation(success=False, error="Payment not verified")
            case "get_address":
                return Observation(success=True, data=self.provider.get_address())
            case "get_network_name":
                return Observation(success=True, data=self.provider.network)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def close(self) -> None:
        await self.provider.close()
