"""
Solana payment provider implementation.
Verifies SOL and USDC (SPL token) payments on Solana blockchain.
"""

import logging
from datetime import datetime
from typing import Any

import httpx
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore

from .interfaces import PaymentProof

logger = logging.getLogger(__name__)

# Solana RPC commitment levels
FINALIZED_COMMITMENT = "finalized"  # ~32 slots confirmation (highest security)

# SPL Token Program IDs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNJbNbNbNbNbNbNbNbNbNbNbNbNbN"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

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

        # Derive Associated Token Account (ATA) for USDC
        # This is the address where USDC payments must be sent
        self.usdc_token_account = self._derive_associated_token_address(
            owner=self.keypair.pubkey(),
            mint=Pubkey.from_string(usdc_mint),
        )

        logger.info(
            "Initialized Solana provider",
            extra={
                "wallet_address": str(self.keypair.pubkey()),
                "usdc_token_account": str(self.usdc_token_account),
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

    def _derive_associated_token_address(self, owner: Pubkey, mint: Pubkey) -> Pubkey:
        """
        Derives the Associated Token Account (ATA) address for a given owner and mint.

        ATAs are deterministic addresses derived from the owner's wallet and token mint.
        This ensures that USDC payments are sent to the correct account.

        Args:
            owner: Owner's public key (our wallet)
            mint: Token mint public key (USDC mint address)

        Returns:
            Associated Token Account public key

        Formula:
            find_program_address([owner, TOKEN_PROGRAM_ID, mint], ASSOCIATED_TOKEN_PROGRAM_ID)
        """
        seeds = [
            bytes(owner),
            bytes(Pubkey.from_string(TOKEN_PROGRAM_ID)),
            bytes(mint),
        ]
        ata, _ = Pubkey.find_program_address(
            seeds, Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
        )
        return ata

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
                is_match, from_address = self._is_matching_payment(
                    tx_detail, amount, memo, currency
                )
                if is_match:
                    proof = self._extract_payment_proof(
                        tx_detail, signature, from_address
                    )
                    logger.info(
                        "Payment verified successfully",
                        extra={
                            "transaction_hash": signature,
                            "amount": amount,
                            "currency": currency,
                            "memo": memo,
                            "from_address": from_address,
                        },
                    )
                    return proof

            logger.info("No matching payment found in recent transactions")
            return None

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(
                "RPC request failed during payment verification",
                extra={"error": str(e), "memo": memo},
                exc_info=True,
            )
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(
                "Failed to parse transaction data",
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
    ) -> tuple[bool, str]:
        """
        Checks if transaction matches payment criteria and extracts source address.

        Args:
            tx_detail: Full transaction details from RPC
            expected_amount: Expected payment amount
            expected_memo: Expected memo string
            currency: "SOL" or "USDC"

        Returns:
            Tuple of (matches, from_address). from_address is empty string if no match.
        """
        # Check for memo instruction
        if not self._has_memo(tx_detail, expected_memo):
            return (False, "")

        # Check for amount match (currency-specific) and extract source
        if currency == "SOL":
            is_match, from_addr = self._has_sol_transfer(tx_detail, expected_amount)
            return (is_match, from_addr)
        elif currency == "USDC":
            is_match, from_addr = self._has_usdc_transfer(tx_detail, expected_amount)
            return (is_match, from_addr)
        else:
            logger.warning("Unsupported currency", extra={"currency": currency})
            return (False, "")

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
        except (KeyError, ValueError, TypeError) as e:
            logger.error("Error parsing memo from transaction", extra={"error": str(e)})
            return False

    def _has_sol_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> tuple[bool, str]:
        """
        Checks if transaction contains SOL transfer to our wallet and extracts sender.

        Args:
            tx_detail: Transaction details
            expected_amount: Expected SOL amount

        Returns:
            Tuple of (matches, from_address). Extracts actual sender from balance changes.
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

            # Find our account index and verify we received the correct amount
            our_idx = None
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
                    if abs(sol_received - expected_amount) < AMOUNT_TOLERANCE:
                        our_idx = idx
                        break

            if our_idx is None:
                return (False, "")

            # Find the sender: analyze balance changes to identify which account sent funds
            # Look for the signer account with the largest balance decrease (excluding recipient)
            sender_addr = ""
            max_decrease = 0

            for idx, key_info in enumerate(account_keys):
                if idx == our_idx:  # Skip recipient account
                    continue

                # Calculate balance change (negative = decrease)
                balance_change = pre_balances[idx] - post_balances[idx]

                # Find signer with largest decrease (actual sender)
                # Note: First account is typically fee payer, but not always the sender
                if balance_change > max_decrease:
                    max_decrease = balance_change
                    pubkey = (
                        key_info
                        if isinstance(key_info, str)
                        else key_info.get("pubkey", "")
                    )
                    sender_addr = pubkey

            return (True, sender_addr)
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.error("Error parsing SOL transfer", extra={"error": str(e)})
            return (False, "")

    def _has_usdc_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> tuple[bool, str]:
        """
        Checks if transaction contains USDC (SPL token) transfer to our wallet.

        Args:
            tx_detail: Transaction details
            expected_amount: Expected USDC amount

        Returns:
            Tuple of (matches, from_address). Extracts source from SPL token instruction.
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

                    # CRITICAL: Verify destination is our Associated Token Account
                    # This prevents attackers from bypassing payment by sending to their own account
                    destination = info.get("destination")
                    if destination != str(self.usdc_token_account):
                        continue

                    # Check if amount matches (USDC has 6 decimals)
                    amount_str = info.get("amount")
                    if amount_str:
                        usdc_amount = int(amount_str) / 1_000_000  # USDC has 6 decimals
                        if abs(usdc_amount - expected_amount) < AMOUNT_TOLERANCE:
                            # Extract source address from the SPL token transfer instruction
                            source_addr = info.get("source", "")
                            # Source is the token account, get authority (owner) if available
                            authority = info.get("authority", source_addr)
                            return (True, authority)

            return (False, "")
        except (KeyError, ValueError, TypeError) as e:
            logger.error("Error parsing USDC transfer", extra={"error": str(e)})
            return (False, "")

    def _extract_payment_proof(
        self, tx_detail: dict[str, Any], signature: str, from_address: str
    ) -> PaymentProof:
        """
        Extracts payment proof from verified transaction.

        Args:
            tx_detail: Transaction details
            signature: Transaction signature
            from_address: Source address extracted from the transfer instruction

        Returns:
            PaymentProof with transaction metadata
        """
        block_time = tx_detail.get("blockTime", 0)
        slot = tx_detail.get("slot", "0")

        return PaymentProof(
            transaction_hash=signature,
            block_number=str(slot),
            from_address=from_address or "unknown",
            confirmed_at=datetime.utcfromtimestamp(block_time)
            if block_time
            else datetime.utcnow(),
        )

    async def close(self):
        """Closes the HTTP client connection."""
        await self.client.aclose()
