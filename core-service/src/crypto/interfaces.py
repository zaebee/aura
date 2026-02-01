"""
Protocol-based interface for blockchain payment providers.
Enables chain-agnostic payment verification architecture.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class PaymentProof:
    """
    Proof of on-chain payment confirmation.
    Used as evidence that a payment was successfully verified.
    """

    transaction_hash: str  # Blockchain transaction ID
    block_number: str  # Block number where transaction was included
    from_address: str  # Payer's wallet address
    confirmed_at: datetime  # Timestamp of confirmation


class CryptoProvider(Protocol):
    """
    Protocol defining the interface for cryptocurrency payment providers.
    Implementations handle chain-specific payment verification logic.

    Example implementations:
    - SolanaProvider: Verifies SOL and SPL token payments on Solana
    - EthereumProvider: Verifies ETH and ERC-20 payments on Ethereum (future)
    - PolygonProvider: Verifies MATIC and ERC-20 on Polygon (future)
    """

    def get_address(self) -> str:
        """
        Returns the wallet address where payments should be sent.

        Returns:
            str: Blockchain-specific wallet address (e.g., Solana public key)
        """
        ...

    def get_network_name(self) -> str:
        """
        Returns the network name for this provider instance.

        Returns:
            str: Network identifier (e.g., "mainnet-beta", "devnet")
        """
        ...

    async def verify_payment(
        self, amount: float, memo: str, currency: str = "SOL"
    ) -> PaymentProof | None:
        """
        Verifies that a payment matching the criteria was received.

        Searches blockchain transactions for a payment to this provider's address
        with the specified amount, memo, and currency. Only returns finalized
        transactions to prevent double-spending attacks.

        Args:
            amount: Expected payment amount (in native units, e.g., SOL or USDC)
            memo: Unique memo string that must be present in the transaction
            currency: Currency code (e.g., "SOL", "USDC", "ETH")

        Returns:
            PaymentProof if payment found and confirmed, None otherwise

        Implementation Notes:
            - MUST only return finalized transactions (not pending/unconfirmed)
            - SHOULD implement reasonable tolerance for floating-point amounts
            - SHOULD cache recent transaction lookups to reduce RPC load
            - MAY implement exponential backoff for RPC rate limiting
        """
        ...
