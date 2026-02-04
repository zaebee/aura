"""
Crypto Protein: Solana payment provider implementation.
Verifies SOL and USDC (SPL token) payments on Solana blockchain.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from aura_core import Observation, SkillProtocol
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore

logger = logging.getLogger(__name__)

# Solana RPC commitment levels
FINALIZED_COMMITMENT = "finalized"  # ~32 slots confirmation (highest security)

# SPL Token Program IDs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNJbNbNbNbNbNbNbNbNbNbNbNbNbN"  # nosec
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"  # nosec

# Amount tolerance for floating-point comparison (0.01%)
AMOUNT_TOLERANCE = 0.0001


class CryptoProtein(SkillProtocol[dict[str, Any], Observation]):
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
    ) -> None:
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

    def get_name(self) -> str:
        return "crypto"

    def get_capabilities(self) -> list[str]:
        return ["verify_payment", "get_address", "get_network_name"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "verify_payment":
            proof = await self.verify_payment(
                amount=params.get("amount", 0.0),
                memo=params.get("memo", ""),
                currency=params.get("currency", "SOL"),
            )
            if proof:
                return Observation(success=True, data={
                    "transaction_hash": proof.get("transaction_hash"),
                    "block_number": proof.get("block_number"),
                    "from_address": proof.get("from_address"),
                    "confirmed_at": proof.get("confirmed_at"),
                })
            return Observation(success=False, error="Payment not verified")
        elif intent == "get_address":
            return Observation(success=True, data=self.get_address())
        elif intent == "get_network_name":
            return Observation(success=True, data=self.get_network_name())

        return Observation(success=False, error=f"Unknown intent: {intent}")

    def get_address(self) -> str:
        """Returns the Solana wallet address (public key)."""
        return str(self.keypair.pubkey())

    def get_network_name(self) -> str:
        """Returns the Solana network name."""
        return self.network

    def _derive_associated_token_address(self, owner: Pubkey, mint: Pubkey) -> Pubkey:
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
    ) -> dict[str, Any] | None:
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

            signatures = await self._get_recent_signatures(limit=100)
            if not signatures:
                logger.warning("No recent transactions found")
                return None

            for sig_info in signatures:
                signature = sig_info["signature"]
                tx_detail = await self._get_transaction(signature)
                if not tx_detail:
                    continue

                is_match, from_address = self._is_matching_payment(
                    tx_detail, amount, memo, currency
                )
                if is_match:
                    proof = self._extract_payment_proof(
                        tx_detail, signature, from_address
                    )
                    return proof

            logger.info("No matching payment found in recent transactions")
            return None

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("RPC request failed", extra={"error": str(e), "memo": memo})
            return None
        except Exception as e:
            logger.error("Failed to verify payment", extra={"error": str(e), "memo": memo})
            return None

    async def _get_recent_signatures(self, limit: int = 100) -> list[dict[str, Any]]:
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
        return data.get("result", [])

    async def _get_transaction(self, signature: str) -> dict[str, Any] | None:
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
        return data.get("result")

    def _is_matching_payment(
        self,
        tx_detail: dict[str, Any],
        expected_amount: float,
        expected_memo: str,
        currency: str,
    ) -> tuple[bool, str]:
        if not self._has_memo(tx_detail, expected_memo):
            return (False, "")

        if currency == "SOL":
            return self._has_sol_transfer(tx_detail, expected_amount)
        elif currency == "USDC":
            return self._has_usdc_transfer(tx_detail, expected_amount)
        return (False, "")

    def _has_memo(self, tx_detail: dict[str, Any], expected_memo: str) -> bool:
        instructions = (
            tx_detail.get("transaction", {})
            .get("message", {})
            .get("instructions", [])
        )
        for instr in instructions:
            if instr.get("program") == "spl-memo":
                if instr.get("parsed") == expected_memo:
                    return True
        return False

    def _has_sol_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> tuple[bool, str]:
        try:
            my_address = str(self.keypair.pubkey())
            post_balances = tx_detail.get("meta", {}).get("postBalances", [])
            pre_balances = tx_detail.get("meta", {}).get("preBalances", [])
            account_keys = (
                tx_detail.get("transaction", {})
                .get("message", {})
                .get("accountKeys", [])
            )

            our_idx = None
            for idx, key_info in enumerate(account_keys):
                pubkey = key_info if isinstance(key_info, str) else key_info.get("pubkey")
                if pubkey == my_address:
                    lamports_received = post_balances[idx] - pre_balances[idx]
                    sol_received = lamports_received / 1_000_000_000
                    if abs(sol_received - expected_amount) < AMOUNT_TOLERANCE:
                        our_idx = idx
                        break

            if our_idx is None:
                return (False, "")

            sender_addr = ""
            max_decrease = 0
            for idx, key_info in enumerate(account_keys):
                if idx == our_idx:
                    continue
                balance_change = pre_balances[idx] - post_balances[idx]
                if balance_change > max_decrease:
                    max_decrease = balance_change
                    sender_addr = key_info if isinstance(key_info, str) else key_info.get("pubkey", "")

            return (True, sender_addr)
        except Exception:
            return (False, "")

    def _has_usdc_transfer(
        self, tx_detail: dict[str, Any], expected_amount: float
    ) -> tuple[bool, str]:
        try:
            instructions = (
                tx_detail.get("transaction", {})
                .get("message", {})
                .get("instructions", [])
            )
            for instr in instructions:
                if (
                    instr.get("program") == "spl-token"
                    and instr.get("parsed", {}).get("type") == "transfer"
                ):
                    info = instr.get("parsed", {}).get("info", {})
                    if info.get("destination") != str(self.usdc_token_account):
                        continue

                    amount_str = info.get("amount")
                    if amount_str:
                        usdc_amount = int(amount_str) / 1_000_000
                        if abs(usdc_amount - expected_amount) < AMOUNT_TOLERANCE:
                            return (True, info.get("authority", info.get("source", "")))
            return (False, "")
        except Exception:
            return (False, "")

    def _extract_payment_proof(
        self, tx_detail: dict[str, Any], signature: str, from_address: str
    ) -> dict[str, Any]:
        block_time = tx_detail.get("blockTime", 0)
        slot = tx_detail.get("slot", "0")

        return {
            "transaction_hash": signature,
            "block_number": str(slot),
            "from_address": from_address or "unknown",
            "confirmed_at": datetime.fromtimestamp(block_time, UTC)
            if block_time
            else datetime.now(UTC),
        }

    async def close(self) -> None:
        await self.client.aclose()
