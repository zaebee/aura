import logging
from decimal import Decimal
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import AsyncWeb3

logger = logging.getLogger(__name__)

# EIP-712 constants for TradeIntent signing
EIP712_DOMAIN_NAME = "HackathonRiskRouter"
EIP712_DOMAIN_VERSION = "1"

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

    def calculate_tax_and_margin(
        self, price: float, margin_rate: float = 0.10
    ) -> dict[str, float]:
        """Apply the Hive Margin rule (The Homeostasis Law)."""
        margin = price * margin_rate
        tax = 0.0  # Future expansion
        return {
            "margin": float(round(margin, 6)),
            "tax": float(round(tax, 6)),
            "total": float(round(price + margin + tax, 6)),
        }


# --- EVM Provider Logic ---


class EVMProvider:
    def __init__(
        self,
        private_key_hex: str,
        rpc_url: str,
        usdc_address: str,
        chain_id: int = 84532,
        risk_router_address: str = "",
    ):
        self.account = Account.from_key(private_key_hex)
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
        self.usdc_address = self.w3.to_checksum_address(usdc_address)
        self.chain_id = chain_id
        self.risk_router_address = (
            self.w3.to_checksum_address(risk_router_address)
            if risk_router_address
            else ""
        )
        # Minimal ERC20 ABI for transfer
        self.usdc_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            }
        ]

    async def transfer_usdc(self, to_address: str, amount: float) -> str:
        """Transfer USDC on EVM (Base Sepolia)."""
        to_address = self.w3.to_checksum_address(to_address)
        contract = self.w3.eth.contract(address=self.usdc_address, abi=self.usdc_abi)

        # USDC usually has 6 decimals
        value = int(Decimal(str(amount)) * Decimal("1e6"))

        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        gas_price = await self.w3.eth.gas_price
        chain_id = await self.w3.eth.chain_id

        # Estimate gas before building the transaction
        gas_estimate = await contract.functions.transfer(
            to_address, value
        ).estimate_gas({"from": self.account.address})

        # Build transaction
        tx = await contract.functions.transfer(to_address, value).build_transaction(
            {
                "chainId": chain_id,
                "gas": gas_estimate,
                "gasPrice": gas_price,
                "nonce": nonce,
            }
        )

        # Sign and send
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex()

    async def sign_eip712_trade_intent(self, trade_intent: dict[str, Any]) -> dict:
        """
        Signs a TradeIntent using EIP-712.
        Follows ERC-8004 genomic sequencing standard.
        """
        if not self.risk_router_address:
            raise ValueError("risk_router_address not configured")

        domain = {
            "name": EIP712_DOMAIN_NAME,
            "version": EIP712_DOMAIN_VERSION,
            "chainId": self.chain_id,
            "verifyingContract": self.risk_router_address,
        }

        # Define EIP-712 types based on TradeIntent protobuf
        types = {
            "TradeIntent": [
                {"name": "trade_id", "type": "string"},
                {"name": "asset_identifier", "type": "string"},
                {"name": "asset_domain", "type": "string"},
                {"name": "proposed_price", "type": "uint256"},
                {"name": "currency_code", "type": "string"},
                {"name": "reasoning", "type": "string"},
            ],
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        }

        # Enforce USDC requirement for simplified decimal conversion
        if trade_intent["currency_code"] != "USDC":
            raise ValueError(
                f"EIP-712 signing currently only supports USDC, but got {trade_intent['currency_code']}"
            )

        # Convert float price to uint256 (assuming 6 decimals for USDC)
        proposed_price_uint = int(
            Decimal(str(trade_intent["proposed_price"])) * Decimal("1e6")
        )

        message = {
            "trade_id": trade_intent["trade_id"],
            "asset_identifier": trade_intent["asset_identifier"],
            "asset_domain": trade_intent["asset_domain"],
            "proposed_price": proposed_price_uint,
            "currency_code": trade_intent["currency_code"],
            "reasoning": trade_intent["reasoning"],
        }

        structured_data = {
            "types": types,
            "domain": domain,
            "primaryType": "TradeIntent",
            "message": message,
        }

        signed_msg = encode_typed_data(full_message=structured_data)
        signature = self.account.sign_message(signed_msg)

        return {
            "signature": signature.signature.hex(),
            "signed_by": self.account.address,
            "structured_data": structured_data,
        }

    async def sign_receipt(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Sign an EIP-712 payload the Membrane built for a decision receipt.

        The payload arrives fully formed rather than being assembled here: the
        Membrane owns what a receipt says, this protein owns the key, and having
        one build a document the other signs blind is how the two drift into
        signing different things.

        Domain separation is what makes reusing the agent's spending key
        acceptable — the receipt domain is not `HackathonRiskRouter`, so a
        receipt signature is not a valid trade authorisation and vice versa.
        That property lives in the payload, so this method must not second-guess
        the domain it was handed.
        """
        signed_msg = encode_typed_data(full_message=payload)
        signature = self.account.sign_message(signed_msg)
        return {
            "signer": self.account.address,
            "signature": signature.signature.hex(),
        }

    async def close(self) -> None:
        # AsyncWeb3 doesn't strictly need close for HTTP provider, but good practice
        pass
