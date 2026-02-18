"""
Metabolic Security: Aromatic Seal for Immutable Audit Trails.

Every event published to NATS can be signed with HMAC-SHA256 to create
an Aromatic (non-repudiable) chronicle.  Subscribers verify the seal
to detect any tampering or replay.

Signature covers: subject + payload + timestamp
Header key:       X-Aura-Sig
"""

import base64
import hashlib
import hmac
import json
from typing import Any


class AuditSigner:
    """
    Aromatic Seal: HMAC-SHA256 signing for NATS audit events.

    Signs:   subject + payload + timestamp (concatenated bytes)
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
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        return str(value).encode("utf-8")

    def sign(self, subject: Any, payload: Any, timestamp: Any) -> str:
        """Produce base64-encoded HMAC-SHA256 signature.

        Defensively coerces all arguments to bytes, healing TypeError from
        callers that forget .encode() or pass non-string/non-bytes values.
        Dicts are serialized as canonical JSON (sort_keys=True) for a stable signature.
        """
        message = (
            self._to_bytes(subject)
            + self._to_bytes(payload)
            + self._to_bytes(timestamp)
        )
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def verify(
        self,
        subject: Any,
        payload: Any,
        timestamp: Any,
        signature: str,
    ) -> bool:
        """
        Verify a signed message.  Returns True if authentic.
        Uses hmac.compare_digest for constant-time comparison.
        """
        expected = self.sign(subject, payload, timestamp)
        return hmac.compare_digest(expected, signature)

    def make_headers(
        self, subject: Any, payload: Any, timestamp: Any
    ) -> dict[str, str]:
        """Convenience: produce the NATS headers dict for a signed publish."""
        return {
            self.HEADER_NAME: self.sign(subject, payload, timestamp),
            self.TIMESTAMP_HEADER: self._to_bytes(timestamp).decode("utf-8"),
        }
