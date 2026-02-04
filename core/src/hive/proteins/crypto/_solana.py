import logging
from datetime import UTC, datetime
from typing import Any

import httpx
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

class SolanaProvider:
    def __init__(
        self,
        private_key_base58: str,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        network: str = "mainnet-beta",
        usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    ) -> None:
        self.keypair = Keypair.from_base58_string(private_key_base58)
        self.rpc_url = rpc_url
        self.network = network
        self.usdc_mint = usdc_mint
        self.client = httpx.AsyncClient(timeout=30.0)

        self.usdc_token_account = self._derive_associated_token_address(
            owner=self.keypair.pubkey(),
            mint=Pubkey.from_string(usdc_mint),
        )

    def get_address(self) -> str:
        return str(self.keypair.pubkey())

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
            signatures = await self._get_recent_signatures(limit=100)
            if not signatures:
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
                    return self._extract_payment_proof(
                        tx_detail, signature, from_address
                    )
            return None
        except Exception as e:
            logger.error(f"Solana verification error: {e}")
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
        return response.json().get("result", [])

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
        return response.json().get("result")

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
        instructions = tx_detail.get("transaction", {}).get("message", {}).get("instructions", [])
        for instr in instructions:
            if instr.get("program") == "spl-memo":
                if instr.get("parsed") == expected_memo:
                    return True
        return False

    def _has_sol_transfer(self, tx_detail: dict[str, Any], expected_amount: float) -> tuple[bool, str]:
        try:
            my_address = self.get_address()
            post_balances = tx_detail.get("meta", {}).get("postBalances", [])
            pre_balances = tx_detail.get("meta", {}).get("preBalances", [])
            account_keys = tx_detail.get("transaction", {}).get("message", {}).get("accountKeys", [])

            our_idx = None
            for idx, key_info in enumerate(account_keys):
                pubkey = key_info if isinstance(key_info, str) else key_info.get("pubkey")
                if pubkey == my_address:
                    sol_received = (post_balances[idx] - pre_balances[idx]) / 1_000_000_000
                    if abs(sol_received - expected_amount) < AMOUNT_TOLERANCE:
                        our_idx = idx
                        break

            if our_idx is None: return (False, "")

            sender_addr = ""
            max_decrease = 0
            for idx, key_info in enumerate(account_keys):
                if idx == our_idx: continue
                balance_change = pre_balances[idx] - post_balances[idx]
                if balance_change > max_decrease:
                    max_decrease = balance_change
                    sender_addr = key_info if isinstance(key_info, str) else key_info.get("pubkey", "")

            return (True, sender_addr)
        except Exception:
            return (False, "")

    def _has_usdc_transfer(self, tx_detail: dict[str, Any], expected_amount: float) -> tuple[bool, str]:
        try:
            instructions = tx_detail.get("transaction", {}).get("message", {}).get("instructions", [])
            for instr in instructions:
                if instr.get("program") == "spl-token" and instr.get("parsed", {}).get("type") == "transfer":
                    info = instr.get("parsed", {}).get("info", {})
                    if info.get("destination") == str(self.usdc_token_account):
                        usdc_amount = int(info.get("amount", 0)) / 1_000_000
                        if abs(usdc_amount - expected_amount) < AMOUNT_TOLERANCE:
                            return (True, info.get("authority", info.get("source", "")))
            return (False, "")
        except Exception:
            return (False, "")

    def _extract_payment_proof(self, tx_detail: dict[str, Any], signature: str, from_address: str) -> dict[str, Any]:
        block_time = tx_detail.get("blockTime", 0)
        return {
            "transaction_hash": signature,
            "block_number": str(tx_detail.get("slot", "0")),
            "from_address": from_address,
            "confirmed_at": datetime.fromtimestamp(block_time, UTC) if block_time else datetime.now(UTC),
        }

    async def close(self) -> None:
        await self.client.aclose()
