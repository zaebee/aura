"""
Secret encryption utilities using Fernet symmetric encryption.

Provides secure encryption/decryption for sensitive data like reservation codes.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretEncryption:
    """
    Handles encryption and decryption of secrets using Fernet symmetric encryption.

    Fernet guarantees that a message encrypted cannot be manipulated or read
    without the key. It uses AES-128 in CBC mode with PKCS7 padding.
    """

    def __init__(self, encryption_key: str):
        """
        Initialize encryption with a base64-encoded key.

        Args:
            encryption_key: Base64-encoded 32-byte key (generate with Fernet.generate_key())

        Raises:
            ValueError: If encryption_key is invalid
        """
        try:
            self.fernet = Fernet(encryption_key.encode())
        except (ValueError, TypeError) as e:
            logger.error("Invalid encryption key format", extra={"error": str(e)})
            raise ValueError(f"Invalid encryption key: {e}") from e

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypts plaintext string to bytes.

        Args:
            plaintext: String to encrypt (e.g., reservation code)

        Returns:
            Encrypted bytes suitable for database storage

        Raises:
            ValueError: If encryption fails
        """
        try:
            return self.fernet.encrypt(plaintext.encode())
        except (ValueError, TypeError, AttributeError) as e:
            logger.error("Encryption failed", extra={"error": str(e)})
            raise ValueError(f"Encryption failed: {e}") from e

    def decrypt(self, ciphertext: bytes) -> str:
        """
        Decrypts encrypted bytes back to plaintext string.

        Args:
            ciphertext: Encrypted bytes from database

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails (wrong key, tampered data)
        """
        try:
            return self.fernet.decrypt(ciphertext).decode()
        except InvalidToken as e:
            logger.error("Decryption failed: invalid token or wrong key")
            raise ValueError("Decryption failed: invalid token or wrong key") from e
        except (ValueError, TypeError, AttributeError) as e:
            logger.error("Decryption failed", extra={"error": str(e)})
            raise ValueError(f"Decryption failed: {e}") from e


def generate_encryption_key() -> str:
    """
    Generates a new Fernet encryption key.

    Use this to create a SECRET_ENCRYPTION_KEY for your environment.

    Returns:
        Base64-encoded encryption key (32 bytes)

    Example:
        >>> key = generate_encryption_key()
        >>> print(f"SECRET_ENCRYPTION_KEY={key}")
    """
    return Fernet.generate_key().decode()
