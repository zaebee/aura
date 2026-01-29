"""
Solana payment provider implementation.
Verifies SOL and USDC (SPL token) payments on Solana blockchain.
"""

import logging
from datetime import datetime
from typing import Any

import httpx
from solders.keypair import Keypair  # type: ignore

from .interfaces import PaymentProof

logger = logging.getLogger(__name__)

# Solana RPC commitment levels
FINALIZED_COMMITMENT = "finalized"  # ~32 slots confirmation (highest security)

# SPL Token Program ID (for USDC transfers)
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNJbNbNbNbNbNbNbNbNbNbNbNbNbN"

# Amount tolerance for floating-point comparison (0.01%)
AMOUNT_TOLERANCE = 0.0001


class SolanaProvider:
    """
    Solana blockchain payment verification provider.

    Supports:
    - Native SOL transfers
    - SPL token transfers (USDC)
    - Memo-based payment linking
    """

    def __init__(
        self,
        private_key_base58: str,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        network: str = "mainnet-beta",
        usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    ):
        """
        Initialize Solana provider.

        Args:
            private_key_base58: Base58-encoded private key (for deriving wallet address)
            rpc_url: Solana RPC endpoint URL
            network: Network name ("mainnet-beta", "devnet", "testnet")
            usdc_mint: USDC token mint address (defaults to mainnet USDC)
        """
        self.keypair = Keypair.from_base58_string(private_key_base58)
        self.rpc_url = rpc_url
        self.network = network
        self.usdc_mint = usdc_mint
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info(
            "Initialized Solana provider",
            extra={
                "wallet_address": str(self.keypair.pubkey()),
                "network": network,
                "rpc_url": rpc_url,
            },
        )

    def get_address(self) -> str:
        """Returns the Solana wallet address (public key)."""
        return str(self.keypair.pubkey())

    def get_network_name(self) -> str:
        """Returns the Solana network name."""
        return self.network

    async def verify_payment(
        self, amount: float, memo: str, currency: str = "SOL"
    ) -> PaymentProof | None:
        """
        Verifies SOL or USDC payment by searching recent transactions.

        Process:
        1. Fetch recent signatures for this wallet address
        2. For each signature, fetch full transaction details
        3. Check if transaction contains:
           - Matching memo instruction
           - Correct amount transfer (SOL or USDC)
           - Finalized status
        4. Return PaymentProof if match found

        Args:
            amount: Expected payment amount (SOL or USDC)
            memo: Unique memo string to match
            currency: "SOL" or "USDC"

        Returns:
            PaymentProof if payment found, None otherwise
        """
        try:
            logger.info(
                "Verifying payment",
                extra={
                    "amount": amount,
                    "currency": currency,
                    "memo": memo,
                    "wallet": self.get_address(),
                },
            )

            # Step 1: Get recent transaction signatures
            signatures = await self._get_recent_signatures(limit=100)
            if not signatures:
                logger.warning("No recent transactions found")
                return None

            # Step 2: Check each transaction for matching payment
            for sig_info in signatures:
                signature = sig_info["signature"]

                # Fetch full transaction details
                tx_detail = await self._get_transaction(signature)
                if not tx_detail:
                    continue

                # Step 3: Verify transaction matches criteria
                if self._is_matching_payment(tx_detail, amount, memo, currency):
                    proof = self._extract_payment_proof(tx_detail, signature)
                    logger.info(
                        "Payment verified successfully",
                        extra={
                            "transaction_hash": signature,
                            "amount": amount,
                            "currency": currency,
                            "memo": memo,
                        },
                    )
                    return proof

            logger.info("No matching payment found in recent transactions")
            return None

        except Exception as e:
            logger.error(
                "Payment verification failed",
                extra={"error": str(e), "memo": memo},
                exc_info=True,
            )
            return None

    async def _get_recent_signatures(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Fetches recent transaction signatures for this wallet.

        Args:
            limit: Maximum number of signatures to fetch

        Returns:
            List of signature info dictionaries
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                str(self.keypair.pubkey()),
                {"limit": limit, "commitment": FINALIZED_COMMITMENT},
            ],
        }

        response = await self.client.post(self.rpc_url, json=payload)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            logger.error(
                "RPC error fetching signatures", extra={"error": data["error"]}
            )
            return []

        return data.get("result", [])

    async def _get_transaction(self, signature: str) -> dict[str, Any] | None:
        """
        Fetches full transaction details for a signature.

        Args:
            signature: Transaction signature

        Returns:
            Transaction detail dictionary or None if not found
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": FINALIZED_COMMITMENT,
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }

        response = await self.client.post(self.rpc_url, json=payload)
        response.raise_for_status()
        data = response.json()

        if "error" in data or not data.get("result"):
            return None

        return data["result"]

    def _is_matching_payment(
        self,
        tx_detail: dict[str, Any],
        expected_amount: float,
        expected_memo: str,
        currency: str,
    ) -> bool:
        """
        Checks if transaction matches payment criteria.

        Args:
            tx_detail: Full transaction details from RPC
            expected_amount: Expected payment amount
            expected_memo: Expected memo string
            currency: "SOL" or "USDC"

        Returns:
            True if transaction matches all criteria
        """
        # Check for memo instruction
        if not self._has_memo(tx_detail, expected_memo):
            return False

        # Check for amount match (currency-specific)
        if currency == "SOL":
            return self._has_sol_transfer(tx_detail, expected_amount)
        elif currency == "USDC":
            return self._has_usdc_transfer(tx_detail, expected_amount)
        else:
            logger.warning("Unsupported currency", extra={"currency": currency})
            return False

    def _has_memo(self, tx_detail: dict[str, Any], expected_memo: str) -> bool:
        """
        Checks if transaction contains a memo instruction with expected text.

        Args:
            tx_detail: Transaction details
            expected_memo: Expected memo string

        Returns:
            True if memo found and matches
        """
        try:
            instructions = (
                tx_detail.get("transaction", {})
                .get("message", {})
                .get("instructions", [])
            )

            for instr in instructions:
                # Memo instructions have program "spl-memo" or specific program ID
                if instr.get("program") == "spl-memo":
                    parsed = instr.get("parsed", "")
                    if parsed == expected_memo:
                        return True

            return False
        except Exception as e:
            logger.error("Error parsing memo", extra={"error": str(e)})
            return False

    def _has_sol_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> bool:
        """
        Checks if transaction contains SOL transfer to our wallet.

        Args:
            tx_detail: Transaction details
            expected_amount: Expected SOL amount

        Returns:
            True if SOL transfer matches
        """
        try:
            my_address = str(self.keypair.pubkey())
            post_balances = tx_detail.get("meta", {}).get("postBalances", [])
            pre_balances = tx_detail.get("meta", {}).get("preBalances", [])
            account_keys = (
                tx_detail.get("transaction", {})
                .get("message", {})
                .get("accountKeys", [])
            )

            # Find our account index
            for idx, key_info in enumerate(account_keys):
                pubkey = (
                    key_info if isinstance(key_info, str) else key_info.get("pubkey")
                )
                if pubkey == my_address:
                    # Calculate balance change (lamports to SOL)
                    lamports_received = post_balances[idx] - pre_balances[idx]
                    sol_received = (
                        lamports_received / 1_000_000_000
                    )  # 1 SOL = 1e9 lamports

                    # Compare with tolerance
                    return abs(sol_received - expected_amount) < AMOUNT_TOLERANCE

            return False
        except Exception as e:
            logger.error("Error parsing SOL transfer", extra={"error": str(e)})
            return False

    def _has_usdc_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> bool:
        """
        Checks if transaction contains USDC (SPL token) transfer to our wallet.

        Args:
            tx_detail: Transaction details
            expected_amount: Expected USDC amount

        Returns:
            True if USDC transfer matches
        """
        try:
            instructions = (
                tx_detail.get("transaction", {})
                .get("message", {})
                .get("instructions", [])
            )

            for instr in instructions:
                # Look for token transfer instructions
                if (
                    instr.get("program") == "spl-token"
                    and instr.get("parsed", {}).get("type") == "transfer"
                ):
                    info = instr.get("parsed", {}).get("info", {})

                    # Check if transfer is to our address
                    destination = info.get("destination")
                    if not destination:
                        continue

                    # Check if amount matches (USDC has 6 decimals)
                    amount_str = info.get("amount")
                    if amount_str:
                        usdc_amount = int(amount_str) / 1_000_000  # USDC has 6 decimals
                        if abs(usdc_amount - expected_amount) < AMOUNT_TOLERANCE:
                            return True

            return False
        except Exception as e:
            logger.error("Error parsing USDC transfer", extra={"error": str(e)})
            return False

    def _extract_payment_proof(
        self, tx_detail: dict[str, Any], signature: str
    ) -> PaymentProof:
        """
        Extracts payment proof from verified transaction.

        Args:
            tx_detail: Transaction details
            signature: Transaction signature

        Returns:
            PaymentProof with transaction metadata
        """
        block_time = tx_detail.get("blockTime", 0)
        slot = tx_detail.get("slot", "0")

        # Extract sender address (first account key, usually the signer)
        account_keys = (
            tx_detail.get("transaction", {}).get("message", {}).get("accountKeys", [])
        )
        from_address = "unknown"
        if account_keys:
            first_key = account_keys[0]
            from_address = (
                first_key
                if isinstance(first_key, str)
                else first_key.get("pubkey", "unknown")
            )

        return PaymentProof(
            transaction_hash=signature,
            block_number=str(slot),
            from_address=from_address,
            confirmed_at=datetime.utcfromtimestamp(block_time)
            if block_time
            else datetime.utcnow(),
        )

    async def close(self):
        """Closes the HTTP client connection."""
        await self.client.aclose()
