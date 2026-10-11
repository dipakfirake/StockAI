"""
Authentication Hardening & Anti-Brute-Force Guard.

Provides:
- Strict password complexity enforcement
- IP and Account Lockout tracking after consecutive failed login attempts
- Security audit event triggering
"""

import time
import re
from typing import Dict, Tuple
from fastapi import HTTPException, status
from backend.core.audit_logger import log_security_event
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
ATTEMPT_WINDOW_SECONDS = 600    # 10 minutes


class BruteForceProtector:
    """In-memory rate tracker for authentication attempts."""
    def __init__(self):
        # Key: "ip:email" -> {"failed_count": int, "first_failed": float, "locked_until": float}
        self._attempts: Dict[str, dict] = {}

    def _get_key(self, ip: str, email: str) -> str:
        return f"{ip.strip()}:{email.strip().lower()}"

    def check_lockout(self, ip: str, email: str):
        """Raise 429 if the IP/account is currently locked out."""
        key = self._get_key(ip, email)
        now = time.time()
        record = self._attempts.get(key)
        if record:
            locked_until = record.get("locked_until", 0)
            if now < locked_until:
                remaining = int(locked_until - now)
                log_security_event(
                    event_type="AUTH_LOCKOUT_BLOCKED",
                    severity="WARNING",
                    ip_address=ip,
                    details={"email": email, "remaining_seconds": remaining},
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Account or IP temporarily locked due to too many failed attempts. Try again in {remaining} seconds.",
                    headers={"Retry-After": str(remaining)},
                )

    def record_failure(self, ip: str, email: str):
        """Record a failed login attempt and apply lockout if threshold exceeded."""
        key = self._get_key(ip, email)
        now = time.time()
        record = self._attempts.get(key)

        if not record or (now - record["first_failed"] > ATTEMPT_WINDOW_SECONDS):
            # Start new attempt window
            self._attempts[key] = {
                "failed_count": 1,
                "first_failed": now,
                "locked_until": 0,
            }
        else:
            record["failed_count"] += 1
            if record["failed_count"] >= MAX_FAILED_ATTEMPTS:
                record["locked_until"] = now + LOCKOUT_DURATION_SECONDS
                log_security_event(
                    event_type="AUTH_ACCOUNT_LOCKED",
                    severity="CRITICAL",
                    ip_address=ip,
                    details={
                        "email": email,
                        "failed_count": record["failed_count"],
                        "lockout_seconds": LOCKOUT_DURATION_SECONDS,
                    },
                )
                logger.warning(f"[Security] Locked {email} from IP {ip} for {LOCKOUT_DURATION_SECONDS}s")

    def record_success(self, ip: str, email: str):
        """Clear failed attempts upon successful login."""
        key = self._get_key(ip, email)
        if key in self._attempts:
            del self._attempts[key]


brute_force_protector = BruteForceProtector()


def validate_password_strength(password: str) -> None:
    """
    Enforce industrial password complexity:
    - At least 8 characters
    - At least one letter (a-z, A-Z)
    - At least one digit or special character
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one alphabetic character.")
    if not re.search(r"[0-9!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain at least one digit or special character.")
