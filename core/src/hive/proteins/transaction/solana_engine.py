import logging
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Finalized
from solders.keypair import Keypair  # type: ignore
from solders.message import Message
from solders.pubkey import Pubkey  # type: ignore
from solders.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    get_associated_token_address,
    transfer_checked,
)

logger = logging.getLogger(__name__)

FINALIZED_COMMITMENT = "finalized"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNJbNbNbNbNbNbNbNbNbNbNbNbNbN"  # nosec
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"  # nosec
AMOUNT_TOLERANCE = 0.0001


class SolanaProvider:
    def __init__(self, private_key_base58: str, rpc_url: str, usdc_mint: str):
        self.keypair = Keypair.from_base58_string(private_key_base58)
        self.rpc_url = rpc_url
        self.usdc_mint = usdc_mint
        self.usdc_mint_pubkey = Pubkey.from_string(usdc_mint)
        self.client = httpx.AsyncClient(timeout=30.0)
        self.async_rpc_client = AsyncClient(rpc_url)
        self.usdc_token_account = self._derive_ata(
            self.keypair.pubkey(), self.usdc_mint_pubkey
        )

    def _derive_ata(self, owner: Pubkey, mint: Pubkey) -> Pubkey:
        return get_associated_token_address(owner, mint)

    async def execute_rwa_collateral(self, wallet_address: str, amount_usdc: float) -> str:
        """
        Execute an SPL Token transfer (USDC) from the Hive Treasury to the user's wallet.
        Simulates the release of a stablecoin loan.
        """
        user_pubkey = Pubkey.from_string(wallet_address)
        user_ata = self._derive_ata(user_pubkey, self.usdc_mint_pubkey)

        # USDC usually has 6 decimals
        amount_raw = int(amount_usdc * 1_000_000)

        logger.info(
            "executing_rwa_collateral",
            to_wallet=wallet_address,
            amount=amount_usdc,
            user_ata=str(user_ata),
        )

        # Construct transfer instruction
        transfer_ix = transfer_checked(
            TransferCheckedParams(
                source=self.usdc_token_account,
                mint=self.usdc_mint_pubkey,
                dest=user_ata,
                owner=self.keypair.pubkey(),
                amount=amount_raw,
                decimals=6,
                program_id=TOKEN_PROGRAM_ID,
            )
        )

        # Build message and transaction using solders
        recent_blockhash = (await self.async_rpc_client.get_latest_blockhash()).value.blockhash
        msg = Message([transfer_ix], self.keypair.pubkey())
        tx = Transaction([self.keypair], msg, recent_blockhash)

        # Send and confirm
        resp = await self.async_rpc_client.send_raw_transaction(bytes(tx))
        tx_sig = resp.value

        logger.info("rwa_collateral_sent", signature=str(tx_sig))

        # Wait for confirmation
        await self.async_rpc_client.confirm_transaction(tx_sig, commitment=Finalized)

        return str(tx_sig)

    async def verify_payment(
        self, amount: float, memo: str, currency: str
    ) -> dict[str, Any] | None:
        signatures = await self._get_signatures()
        for sig_info in signatures:
            tx = await self._get_tx(sig_info["signature"])
            if not tx:
                continue
            is_match, from_addr = self._check_match(tx, amount, memo, currency)
            if is_match:
                return self._get_proof(tx, sig_info["signature"], from_addr)
        return None

    async def _get_signatures(self) -> list[dict[str, Any]]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                str(self.keypair.pubkey()),
                {"limit": 20, "commitment": FINALIZED_COMMITMENT},
            ],
        }
        r = await self.client.post(self.rpc_url, json=payload)
        return cast(list[dict[str, Any]], r.json().get("result", []))

    async def _get_tx(self, sig: str) -> dict[str, Any] | None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                sig,
                {
                    "encoding": "jsonParsed",
                    "commitment": FINALIZED_COMMITMENT,
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        r = await self.client.post(self.rpc_url, json=payload)
        return cast(dict[str, Any] | None, r.json().get("result"))

    def _check_match(
        self, tx: dict, amt: float, memo: str, curr: str
    ) -> tuple[bool, str]:
        # Simple memo check
        has_memo = False
        for instr in (
            tx.get("transaction", {}).get("message", {}).get("instructions", [])
        ):
            if instr.get("program") == "spl-memo" and instr.get("parsed") == memo:
                has_memo = True
                break
        if not has_memo:
            return False, ""

        if curr == "SOL":
            return self._check_sol(tx, amt)
        return self._check_usdc(tx, amt)

    def _check_sol(self, tx: dict, amt: float) -> tuple[bool, str]:
        meta = tx.get("meta", {})
        post = meta.get("postBalances", [])
        pre = meta.get("preBalances", [])
        keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        my_addr = str(self.keypair.pubkey())
        for i, k in enumerate(keys):
            pub = k if isinstance(k, str) else k.get("pubkey")
            if pub == my_addr:
                if abs((post[i] - pre[i]) / 1e9 - amt) < AMOUNT_TOLERANCE:
                    # find sender (biggest decrease)
                    sender = ""
                    max_d = 0
                    for j, k2 in enumerate(keys):
                        if i == j:
                            continue
                        d = pre[j] - post[j]
                        if d > max_d:
                            max_d = d
                            sender = k2 if isinstance(k2, str) else k2.get("pubkey", "")
                    return True, sender
        return False, ""

    def _check_usdc(self, tx: dict, amt: float) -> tuple[bool, str]:
        for instr in (
            tx.get("transaction", {}).get("message", {}).get("instructions", [])
        ):
            if (
                instr.get("program") == "spl-token"
                and instr.get("parsed", {}).get("type") == "transfer"
            ):
                info = instr.get("parsed", {}).get("info", {})
                if info.get("destination") == str(self.usdc_token_account):
                    if abs(int(info.get("amount", 0)) / 1e6 - amt) < AMOUNT_TOLERANCE:
                        return True, info.get("authority", info.get("source", ""))
        return False, ""

    def _get_proof(self, tx: dict, sig: str, addr: str) -> dict:
        return {
            "transaction_hash": sig,
            "block_number": str(tx.get("slot", 0)),
            "from_address": addr or "unknown",
            "confirmed_at": datetime.fromtimestamp(tx.get("blockTime", 0), UTC)
            if tx.get("blockTime")
            else datetime.now(UTC),
        }

    def generate_payment_request(
        self,
        amount: float,
        memo: str,
        currency: str,
        label: str = "Aura Hive",
        message: str = "Payment",
    ) -> str:
        from urllib.parse import quote
        recipient = str(self.keypair.pubkey())

        base_url = f"solana:{recipient}"
        params = [
            f"amount={amount}",
            f"label={quote(label)}",
            f"message={quote(message)}",
            f"memo={quote(memo)}",
        ]
        if currency == "USDC":
            params.append(f"spl-token={self.usdc_mint}")

        return f"{base_url}?{'&'.join(params)}"

    async def close(self) -> None:
        await self.client.aclose()
        await self.async_rpc_client.close()
