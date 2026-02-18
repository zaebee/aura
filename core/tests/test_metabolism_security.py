import hmac as hmac_module
from typing import Any

import pytest
from src.hive.metabolism.security import AuditSigner

SUBJECT = "aura.wallet.sanctify"
PAYLOAD = b'{"wallet": "0xDEAD"}'
TIMESTAMP = "2026-02-12T00:00:00Z"
KEY = "super-secret-key"


def test_sign_verify_roundtrip() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, PAYLOAD, TIMESTAMP)
    assert signer.verify(SUBJECT, PAYLOAD, TIMESTAMP, sig) is True


def test_verify_tampered_payload_returns_false() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, PAYLOAD, TIMESTAMP)
    tampered = b'{"wallet": "0xBEEF"}'
    assert signer.verify(SUBJECT, tampered, TIMESTAMP, sig) is False


def test_verify_tampered_subject_returns_false() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, PAYLOAD, TIMESTAMP)
    assert signer.verify("aura.wallet.evil", PAYLOAD, TIMESTAMP, sig) is False


def test_verify_tampered_timestamp_returns_false() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, PAYLOAD, TIMESTAMP)
    assert signer.verify(SUBJECT, PAYLOAD, "2099-01-01T00:00:00Z", sig) is False


def test_verify_wrong_signature_returns_false() -> None:
    signer = AuditSigner(KEY)
    assert signer.verify(SUBJECT, PAYLOAD, TIMESTAMP, "bm90YXJlYWxzaWc=") is False


def test_empty_signing_key_raises() -> None:
    with pytest.raises(ValueError, match="signing_key must not be empty"):
        AuditSigner("")


def test_make_headers_contains_both_keys() -> None:
    signer = AuditSigner(KEY)
    headers = signer.make_headers(SUBJECT, PAYLOAD, TIMESTAMP)
    assert AuditSigner.HEADER_NAME in headers
    assert AuditSigner.TIMESTAMP_HEADER in headers
    assert headers[AuditSigner.TIMESTAMP_HEADER] == TIMESTAMP


def test_compare_digest_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify timing-safe comparison is used in verify()."""
    calls: list[Any] = []
    original = hmac_module.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(hmac_module, "compare_digest", spy)

    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, PAYLOAD, TIMESTAMP)
    signer.verify(SUBJECT, PAYLOAD, TIMESTAMP, sig)

    assert len(calls) == 1, "hmac.compare_digest should be called exactly once"


def test_sign_accepts_non_string_subject() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(42, PAYLOAD, TIMESTAMP)
    assert isinstance(sig, str) and len(sig) > 0


def test_sign_accepts_bytes_subject() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(b"aura.wallet.sanctify", PAYLOAD, TIMESTAMP)
    expected = signer.sign("aura.wallet.sanctify", PAYLOAD, TIMESTAMP)
    assert sig == expected


def test_sign_accepts_non_string_payload() -> None:
    signer = AuditSigner(KEY)
    sig = signer.sign(SUBJECT, {"wallet": "0xDEAD"}, TIMESTAMP)
    assert isinstance(sig, str) and len(sig) > 0


def test_sign_accepts_non_string_timestamp() -> None:
    import datetime

    signer = AuditSigner(KEY)
    ts = datetime.datetime(2026, 2, 12, tzinfo=datetime.UTC)
    sig = signer.sign(SUBJECT, PAYLOAD, ts)
    assert isinstance(sig, str) and len(sig) > 0
