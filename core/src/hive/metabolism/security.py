"""
Metabolic Security: Aromatic Seal for Immutable Audit Trails.

Every event published to NATS can be signed with HMAC-SHA256 to create
an Aromatic (non-repudiable) chronicle.  Subscribers verify the seal
to detect any tampering or replay.

Signature covers: subject + serialized_payload_bytes + iso_timestamp
Header key:       X-Aura-Sig
"""

import base64
import hashlib
import hmac
from typing import Any


class AuditSigner:
    """
    Aromatic Seal: HMAC-SHA256 signing for NATS audit events.

    Signs:   subject + payload_bytes + timestamp_iso (concatenated bytes)
    Verifies using hmac.compare_digest (constant-time, timing-safe).
    """

    HEADER_NAME: str = "X-Aura-Sig"
    TIMESTAMP_HEADER: str = "X-Aura-Timestamp"

    def __init__(self, signing_key: str) -> None:
        if not signing_key:
            raise ValueError("AuditSigner: signing_key must not be empty.")
        self._key: bytes = signing_key.encode("utf-8")

    @staticmethod
    def _to_bytes(value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    def sign(self, subject: Any, payload_bytes: Any, timestamp_iso: Any) -> str:
        """Produce base64-encoded HMAC-SHA256 signature.

        Defensively coerces all arguments to bytes, healing TypeError from
        callers that forget .encode() or pass non-string/non-bytes values.
        """
        message = (
            self._to_bytes(subject)
            + self._to_bytes(payload_bytes)
            + self._to_bytes(timestamp_iso)
        )
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def verify(
        self,
        subject: str,
        payload_bytes: bytes,
        timestamp_iso: str,
        signature: str,
    ) -> bool:
        """
        Verify a signed message.  Returns True if authentic.
        Uses hmac.compare_digest for constant-time comparison.
        """
        expected = self.sign(subject, payload_bytes, timestamp_iso)
        return hmac.compare_digest(expected, signature)

    def make_headers(
        self, subject: str, payload_bytes: bytes, timestamp_iso: str
    ) -> dict[str, str]:
        """Convenience: produce the NATS headers dict for a signed publish."""
        return {
            self.HEADER_NAME: self.sign(subject, payload_bytes, timestamp_iso),
            self.TIMESTAMP_HEADER: timestamp_iso,
        }
