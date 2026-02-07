import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

import httpx
from cryptography.fernet import Fernet, InvalidToken
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore

logger = logging.getLogger(__name__)

# --- Encryption Logic ---


class SecretEncryption:
    def __init__(self, encryption_key: str):
        try:
            self.fernet = Fernet(encryption_key.encode())
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid encryption key: {e}") from e

    def encrypt(self, plaintext: str) -> bytes:
        return self.fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self.fernet.decrypt(ciphertext).decode()
        except InvalidToken:
            raise ValueError("Decryption failed: invalid token") from None


# --- Pricing Logic ---

CryptoCurrency = Literal["SOL", "USDC"]


class PriceConverter:
    FIXED_RATES = {
        "SOL": Decimal("100.0"),
        "USDC": Decimal("1.0"),
    }

    def convert_usd_to_crypto(
        self, usd_amount: float, crypto_currency: CryptoCurrency
    ) -> float:
        if crypto_currency not in self.FIXED_RATES:
            raise ValueError(f"Unsupported currency: {crypto_currency}")
        return float(Decimal(str(usd_amount)) / self.FIXED_RATES[crypto_currency])


# --- Solana Provider Logic ---

FINALIZED_COMMITMENT = "finalized"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNJbNbNbNbNbNbNbNbNbNbNbNbNbN"  # nosec
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"  # nosec
AMOUNT_TOLERANCE = 0.0001


class SolanaProvider:
    def __init__(self, private_key_base58: str, rpc_url: str, usdc_mint: str):
        self.keypair = Keypair.from_base58_string(private_key_base58)
        self.rpc_url = rpc_url
        self.usdc_mint = usdc_mint
        self.client = httpx.AsyncClient(timeout=30.0)
        self.usdc_token_account = self._derive_ata(
            self.keypair.pubkey(), Pubkey.from_string(usdc_mint)
        )

    def _derive_ata(self, owner: Pubkey, mint: Pubkey) -> Pubkey:
        seeds = [bytes(owner), bytes(Pubkey.from_string(TOKEN_PROGRAM_ID)), bytes(mint)]
        ata, _ = Pubkey.find_program_address(
            seeds, Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
        )
        return ata

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

    async def close(self) -> None:
        await self.client.aclose()
