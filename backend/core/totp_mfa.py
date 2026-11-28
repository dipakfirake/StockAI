"""
TOTP Authenticator MFA (`pyotp` RFC 6238), single-use recovery codes,
and offline SVG QR generation (zero third-party QR image network leakage).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import struct
import time
from typing import Tuple

try:
    import pyotp
except ImportError:  # pragma: no cover - fallback ensures local/CI resilience
    pyotp = None

try:
    import qrcode
    import qrcode.image.svg
except ImportError:  # pragma: no cover
    qrcode = None

from backend.core.config import settings


def generate_totp_secret() -> str:
    """Generate a cryptographically random 160-bit Base32 TOTP seed."""
    if pyotp is not None:
        return pyotp.random_base32()
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def get_otpauth_uri(secret: str, account_email: str, issuer: str = "StockAI Admin") -> str:
    """Build standard otpauth://totp/ URI for Google Authenticator / Authy / 1Password."""
    if pyotp is not None:
        return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=issuer)
    from urllib.parse import quote
    label = quote(f"{issuer}:{account_email}")
    iss = quote(issuer)
    return f"otpauth://totp/{label}?secret={secret}&issuer={iss}&algorithm=SHA1&digits=6&period=30"


def format_secret_blocks(secret: str) -> str:
    """Format Base32 seed in readable 4-character groups for manual authenticator entry."""
    clean = (secret or "").strip().upper().replace(" ", "")
    return " ".join(clean[i : i + 4] for i in range(0, len(clean), 4))


def generate_qr_svg_data_uri(uri: str) -> str | None:
    """Render an offline SVG QR data URI cleanly without sending secrets to external URLs."""
    if qrcode is None or not uri:
        return None
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    svg_bytes = buf.getvalue()
    b64 = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _rfc6238_code(secret: str, counter: int) -> str:
    padded = secret.strip().upper().replace(" ", "")
    pad_len = (-len(padded)) % 8
    key = base64.b32decode(padded + ("=" * pad_len))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code_int:06d}"


def verify_totp_code(secret: str | None, code: str | None, *, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP authenticator code with +/- valid_window clock drift tolerance."""
    if not secret or not code:
        return False
    clean_code = "".join(ch for ch in str(code).strip() if ch.isdigit())
    if len(clean_code) != 6:
        return False
    if pyotp is not None:
        try:
            return bool(pyotp.TOTP(secret).verify(clean_code, valid_window=valid_window))
        except Exception:
            return False

    now_step = int(time.time() // 30)
    for offset in range(-valid_window, valid_window + 1):
        expected = _rfc6238_code(secret, now_step + offset)
        if hmac.compare_digest(expected, clean_code):
            return True
    return False


def _hash_recovery_code(raw_code: str) -> str:
    normalized = raw_code.strip().upper().replace("-", "").replace(" ", "")
    key = f"{settings.SECRET_KEY}:mfa-recovery-v1".encode("utf-8")
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_recovery_codes(count: int = 8) -> Tuple[list[str], str]:
    """Generate `count` single-use backup codes (`XXXX-XXXX`) and return `(plaintext_list, json_hashes)`."""
    plain_codes: list[str] = []
    hashed_codes: list[str] = []
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(count):
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        code = f"{part1}-{part2}"
        plain_codes.append(code)
        hashed_codes.append(_hash_recovery_code(code))
    return plain_codes, json.dumps(hashed_codes)


def consume_recovery_code(stored_hashes_json: str | None, candidate_code: str | None) -> Tuple[bool, str]:
    """
    Validate and atomically remove a single-use backup code from `stored_hashes_json`.
    Returns `(matched: bool, updated_json: str)`.
    """
    if not stored_hashes_json or not candidate_code:
        return False, stored_hashes_json or "[]"
    try:
        hashes: list[str] = json.loads(stored_hashes_json)
        if not isinstance(hashes, list):
            return False, "[]"
    except Exception:
        return False, "[]"

    target_hash = _hash_recovery_code(candidate_code)
    for idx, existing_hash in enumerate(hashes):
        if isinstance(existing_hash, str) and hmac.compare_digest(existing_hash, target_hash):
            remaining = hashes[:idx] + hashes[idx + 1 :]
            return True, json.dumps(remaining)
    return False, stored_hashes_json
