"""
Agent Identity Module for Aura Platform

Provides cryptographic key management and message signing using Ed25519.
"""

import json
import time
from typing import Any

import nacl.encoding
import nacl.signing


class AgentWallet:
    """
    Agent wallet for key management and message signing using Ed25519.

    This class handles:
    - Key generation and management
    - Message signing for API requests
    - DID (Decentralized Identifier) creation
    - Signature verification
    """

    def __init__(self, private_key_hex: str = None, public_key_hex: str = None):
        """
        Initialize agent wallet with existing keys or generate new ones.

        Args:
            private_key_hex: Hex-encoded private key (optional)
            public_key_hex: Hex-encoded public key (optional)

        If no keys are provided, a new key pair is generated.
        """
        if private_key_hex:
            # Load existing private key
            private_key_bytes = bytes.fromhex(private_key_hex)
            self.signing_key = nacl.signing.SigningKey(private_key_bytes)
            self.verify_key = self.signing_key.verify_key
        elif public_key_hex:
            # Load existing public key (view-only mode)
            public_key_bytes = bytes.fromhex(public_key_hex)
            self.verify_key = nacl.signing.VerifyKey(public_key_bytes)
            self.signing_key = None
        else:
            # Generate new key pair
            self.signing_key = nacl.signing.SigningKey.generate()
            self.verify_key = self.signing_key.verify_key

    @property
    def did(self) -> str:
        """Return Decentralized Identifier (DID) for this agent."""
        return f"did:key:{self.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()}"

    @property
    def private_key_hex(self) -> str:
        """Return private key as hex string."""
        if not self.signing_key:
            raise ValueError("This wallet is in view-only mode (no private key)")
        return self.signing_key.encode(encoder=nacl.encoding.HexEncoder).decode()

    @property
    def public_key_hex(self) -> str:
        """Return public key as hex string."""
        return self.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()

    def sign_request(
        self, method: str, path: str, body: dict[str, Any]
    ) -> tuple[str, str, str]:
        """
        Sign a request and return security headers.

        Args:
            method: HTTP method (e.g., "POST")
            path: Request path (e.g., "/v1/negotiate")
            body: Request body as dictionary

        Returns:
            Tuple of (X-Agent-ID, X-Timestamp, X-Signature)

        Raises:
            ValueError: If wallet is in view-only mode
        """
        if not self.signing_key:
            raise ValueError("Cannot sign without private key")

        # Generate timestamp (Unix timestamp in seconds)
        timestamp = str(int(time.time()))

        # Canonicalize body as JSON (sorted keys, no spaces)
        body_json = json.dumps(body, sort_keys=True, separators=(",", ":"))
        body_hash = self._hash_body(body_json)

        # Create message to sign: METHOD + PATH + TIMESTAMP + BODY_HASH
        message = f"{method}{path}{timestamp}{body_hash}"

        # Sign the message
        signed = self.signing_key.sign(
            message.encode("utf-8"), encoder=nacl.encoding.HexEncoder
        )
        signature = signed.signature.decode("utf-8")  # Extract just the signature part

        return self.did, timestamp, signature

    def _hash_body(self, body_json: str) -> str:
        """Hash the request body using SHA-256."""
        import hashlib

        return hashlib.sha256(body_json.encode("utf-8")).hexdigest()

    @staticmethod
    def from_did(did: str) -> "AgentWallet":
        """
        Create a view-only wallet from a DID.

        Args:
            did: Decentralized Identifier (e.g., "did:key:public_key_hex")

        Returns:
            AgentWallet instance in view-only mode

        Raises:
            ValueError: If DID format is invalid
        """
        if not did.startswith("did:key:"):
            raise ValueError(f"Invalid DID format: {did}")

        public_key_hex = did[8:]  # Remove "did:key:" prefix
        return AgentWallet(public_key_hex=public_key_hex)

    def verify_signature(self, message: str, signature_hex: str) -> bool:
        """
        Verify a signature using this agent's public key.

        Args:
            message: Original message that was signed
            signature_hex: Hex-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            signature_bytes = bytes.fromhex(signature_hex)
            self.verify_key.verify(message.encode("utf-8"), signature_bytes)
            return True
        except nacl.exceptions.BadSignatureError:
            return False
        except Exception:
            return False


def generate_test_wallet() -> AgentWallet:
    """
    Generate a test wallet for development and testing.

    Returns:
        AgentWallet with pre-generated keys for testing
    """
    # This is a test wallet - in production, each agent should generate their own
    wallet = AgentWallet()
    print("🔑 Generated test wallet:")
    print(f"   DID: {wallet.did}")
    print(f"   Public Key: {wallet.public_key_hex}")
    print(f"   Private Key: {wallet.private_key_hex}")
    return wallet
