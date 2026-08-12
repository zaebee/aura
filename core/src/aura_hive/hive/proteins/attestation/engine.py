from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data


class AttestationEngine:
    """
    The key, and nothing else.

    Deliberately has no RPC client, no chain connection and no `web3` import.
    Signing an EIP-712 payload needs an account and the encoder; the provider
    this was extracted from built an `AsyncWeb3` connection, checksummed token
    addresses and loaded an ERC20 ABI, none of which signing ever touched.
    """

    def __init__(self, private_key_hex: str) -> None:
        self.account = Account.from_key(private_key_hex)

    @property
    def address(self) -> str:
        """The signer, readable before anything has been signed."""
        return str(self.account.address)

    def sign(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Sign the payload as handed over.

        The document arrives fully formed. The Membrane owns what a receipt
        says and this owns the key, and the domain in the payload is what makes
        a receipt signature unusable as any other kind of authorisation — so
        this must not second-guess the domain it was given.
        """
        signed_message = encode_typed_data(full_message=payload)
        signature = self.account.sign_message(signed_message)
        return {
            "signer": str(self.account.address),
            "signature": signature.signature.hex(),
        }
