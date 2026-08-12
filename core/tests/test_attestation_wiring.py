"""
A deployment must be able to tell, at boot, whether it is attesting.

Before this, the only evidence that production was not signing was a
`membrane_receipt_unsigned` warning on every receipt — a symptom, not a
statement. The difference between "we chose not to attest" and "we believed we
were attesting" belongs in the startup log.
"""

from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
from eth_account import Account
from structlog.testing import capture_logs


def build_attestation(settings_key: str) -> tuple[AttestationSkill | None, list[str]]:
    """
    Calls the Cortex's own decision function and captures what it logged.

    `capture_logs` rather than a hand-rolled processor: configuring one
    replaces the whole chain including the renderer, so the logger is handed a
    dict where it expects a rendered string and raises. It also restores the
    previous configuration on exit, which a manual `reset_defaults()` does not
    — that resets to *defaults*, not to whatever the suite had.

    The Cortex import is deferred into the body: importing `cortex` at module
    scope pulls in dspy, redis, sqlalchemy and the OpenTelemetry instrumentors,
    which this test has no use for.
    """
    from aura_hive.config.attestation import AttestationSettings
    from aura_hive.hive.cortex import build_attestation as _build

    with capture_logs() as entries:
        skill = _build(settings_key, AttestationSettings())

    return skill, [str(entry.get("event", "")) for entry in entries]


class TestTheProteinIsRegisteredOnlyWithAKey:
    def test_a_configured_key_produces_a_bound_protein(self) -> None:
        account = Account.create()

        skill, events = build_attestation(account.key.hex())

        assert skill is not None
        assert skill.get_name() == "attestation"
        assert "attestation_signer_ready" in events

    def test_no_key_produces_no_protein_and_says_so(self) -> None:
        skill, events = build_attestation("")

        assert skill is None
        assert "attestation_disabled_no_key" in events

    def test_a_key_with_surrounding_whitespace_still_works(self) -> None:
        """
        `printf` versus `echo` into a secret is the difference, and a trailing
        newline is the most common way a real key arrives malformed. Without a
        strip it is indistinguishable from a corrupt key: the cell refuses to
        boot over an invisible character.
        """
        account = Account.create()

        skill, events = build_attestation(f"  {account.key.hex()}\n")

        assert skill is not None
        assert "attestation_signer_ready" in events

    def test_a_corrupt_key_names_the_setting_and_not_the_key(self) -> None:
        """
        Refusing to boot is right — the alternative is a deployment that
        believes it attests. But the operator has to be told which setting is
        wrong, and must not be told what the value was.
        """
        import pytest

        with pytest.raises(ValueError) as caught:
            build_attestation("not-a-key-at-all")

        message = str(caught.value)
        assert "AURA_ATTESTATION__PRIVATE_KEY" in message
        assert "not-a-key-at-all" not in message

    def test_the_startup_line_carries_the_address_not_the_key(self) -> None:
        """
        The address is the durable fact — it is what a signature recovers to,
        and what the provenance record ties to an environment. The key must
        never reach a log line.
        """
        account = Account.create()
        engine = AttestationEngine(account.key.hex())

        assert engine.address == account.address
        assert account.key.hex() not in engine.address
