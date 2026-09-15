"""Secret encryption intents: encrypt, decrypt."""

from typing import Any

from aura_core import make_struct
from aura_core_gen.aura.core.v1 import Observation

from ..engine import SecretEncryption


class SecretsHandlers:
    """Secrets domain. Owns only the encryption primitive."""

    # Class-level contract (no string method refs: bandit B105
    # mistakes "_*_secret" for a hardcoded password).
    INTENTS: tuple[str, ...] = ("encrypt_secret", "decrypt_secret")

    def __init__(self, encryption: SecretEncryption | None) -> None:
        self.encryption = encryption
        self.capabilities = {
            "encrypt_secret": self._encrypt_secret,
            "decrypt_secret": self._decrypt_secret,
        }

    async def _encrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        encrypted = self.encryption.encrypt(params["secret"])
        return Observation(
            success=True,
            metadata=make_struct({"encrypted_secret": str(encrypted)}),
        )

    async def _decrypt_secret(self, params: dict[str, Any]) -> Observation:
        assert self.encryption is not None
        decrypted = self.encryption.decrypt(params["encrypted_secret"])
        return Observation(
            success=True,
            metadata=make_struct({"decrypted_secret": str(decrypted)}),
        )
