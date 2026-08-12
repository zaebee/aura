from pydantic import BaseModel, SecretStr


class AttestationSettings(BaseModel):
    """
    The key that signs decision receipts, and the domain it signs under.

    Separate from `CryptoSettings` deliberately. Attesting a decision and
    moving money are different jobs with different blast radii, and the flag
    that gated signing was a flag about payment locks: a deployment wanting
    attested receipts had to turn on crypto and supply a Solana key and a
    Fernet key it never used.

    There is no `enabled` field. The protein is registered when a key is
    present and not otherwise, so there is no way to configure "on but not
    working" — which is the state this section exists to remove.
    """

    private_key: SecretStr = SecretStr("")

    # Required by EIP-712's domain separator; nothing is submitted on-chain.
    # The signature block on a receipt records the chain id it was signed
    # under, and `verify()` rebuilds the domain from the receipt itself, so
    # changing this does not invalidate receipts already signed.
    chain_id: int = 84532
