"""
Attestation is configured on its own, not through the payments section.

Signing a decision receipt needs one key. Reaching it through `CryptoSettings`
meant a deployment that wanted attestation had to enable crypto payment locks
and supply a Solana key and a Fernet key it had no use for.
"""

from aura_hive.config import Settings
from aura_hive.config.attestation import AttestationSettings
from pydantic import SecretStr


def test_the_defaults_leave_attestation_off() -> None:
    settings = AttestationSettings()

    assert settings.private_key.get_secret_value() == ""
    assert settings.chain_id == 84532


def test_attestation_hangs_off_the_root_settings() -> None:
    settings = Settings()

    assert isinstance(settings.attestation, AttestationSettings)


def test_a_key_is_carried_as_a_secret() -> None:
    """A SecretStr so the key cannot reach a log line by being interpolated."""
    settings = AttestationSettings(private_key=SecretStr("0xdeadbeef"))

    assert "deadbeef" not in repr(settings)
    assert settings.private_key.get_secret_value() == "0xdeadbeef"
