"""
Application-level Fernet (AES-128-CBC + HMAC-SHA256) encryption at rest
for sensitive database secrets (Fyers broker tokens, API secrets, and TOTP seeds).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

_ENC_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    """Derive a valid 32-byte URL-safe Fernet key from SETTINGS_ENCRYPTION_KEY or SECRET_KEY."""
    configured = (getattr(settings, "SETTINGS_ENCRYPTION_KEY", None) or "").strip()
    if configured:
        try:
            raw = configured.encode("utf-8")
            # Accept either a pre-formatted 44-char Fernet key or arbitrary passphrase
            if len(raw) == 44:
                return Fernet(raw)
        except Exception:
            pass
        digest = hashlib.sha256(configured.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    material = f"{settings.SECRET_KEY}:stockai-aes-at-rest-v1".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted_secret(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt_secret(plaintext: str | None) -> str:
    """Encrypt plaintext string into `enc:v1:<fernet-token>` idempotently."""
    if not plaintext:
        return ""
    raw = str(plaintext).strip()
    if not raw or is_encrypted_secret(raw):
        return raw
    token = _get_fernet().encrypt(raw.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_secret(stored_value: str | None) -> str:
    """
    Decrypt `enc:v1:...` secrets transparently.
    Gracefully returns legacy unencrypted values unchanged so migrations remain zero-downtime.
    """
    if not stored_value:
        return ""
    raw = str(stored_value).strip()
    if not is_encrypted_secret(raw):
        return raw
    token = raw[len(_ENC_PREFIX):].encode("utf-8")
    try:
        return _get_fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        logger.warning("Could not decrypt stored secret (%s); verify SECRET_KEY / SETTINGS_ENCRYPTION_KEY.", exc)
        return ""
