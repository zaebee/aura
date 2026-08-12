from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data

# A payload with no meaning, signed once at construction to prove the key can
# produce a signature that recovers. Deliberately not a receipt shape: nothing
# should be able to mistake the probe's output for an attestation.
_PROBE: dict[str, Any] = {
    "types": {
        "EIP712Domain": [{"name": "name", "type": "string"}],
        "KeyProbe": [{"name": "content", "type": "string"}],
    },
    "domain": {"name": "AuraAttestationKeyProbe"},
    "primaryType": "KeyProbe",
    "message": {"content": "probe"},
}


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

        # Prove the key signs recoverably before anything relies on it.
        #
        # `Account.from_key` is not enough. It accepts the all-zero scalar —
        # the value a secret template or an unset CI variable seeds — returns
        # an address for it, and signs 65 bytes that no recovery accepts. A
        # deployment holding that key announces a signer at boot, stamps
        # receipts `AURA-RECEIPT-V2`, and every one of them fails `verify()`:
        # it believes it attests while producing a worthless corpus, which is
        # strictly worse than the honest unsigned state this protein replaces.
        #
        # Signing and recovering rather than range-checking the scalar, so any
        # degenerate key the library mishandles is caught rather than the one
        # example that prompted this.
        probe = encode_typed_data(full_message=_PROBE)
        try:
            recovered = Account.recover_message(
                probe, signature=self.account.sign_message(probe).signature
            )
        except Exception as exc:
            raise ValueError(
                "attestation key cannot produce a recoverable signature"
            ) from exc

        if recovered != self.account.address:
            raise ValueError(
                "attestation key cannot produce a recoverable signature: "
                "it recovers to a different address than it reports"
            )

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
