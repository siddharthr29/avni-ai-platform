"""Fernet symmetric encryption for sensitive data at rest."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def get_fernet() -> Fernet:
    """Get Fernet instance. Key derived from JWT_SECRET via SHA-256."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a Fernet token string."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token string back to plaintext.

    If decryption fails (e.g. data was stored before encryption was enabled),
    returns the original string as-is and logs a warning.
    """
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as e:
        # Graceful fallback: if the value isn't a valid Fernet token,
        # it's likely a plaintext key from before encryption was enabled.
        logger.warning("Failed to decrypt value (may be plaintext from before encryption): %s", type(e).__name__)
        return ciphertext
