"""
Structured Security & Financial Audit Trail.

Maintains an immutable, structured event log of all security, authentication,
and financial order operations for forensic analysis and compliance.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

AUDIT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
AUDIT_LOG_PATH = os.path.join(AUDIT_LOG_DIR, "security_audit.log")

# Setup dedicated file handler for audit logs
audit_logger = logging.getLogger("security.audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False  # Keep separate from general debug noise

if not audit_logger.handlers:
    fh = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(fh)


def log_security_event(
    event_type: str,
    severity: str = "INFO",
    ip_address: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
):
    """
    Record an immutable structured audit log entry in JSON format.
    
    Args:
        event_type: e.g. 'AUTH_LOGIN_SUCCESS', 'ORDER_EXECUTED', 'RATE_LIMIT_BLOCKED'
        severity: 'INFO', 'WARNING', 'CRITICAL'
        ip_address: Client IP address
        user_id: Authenticated user identifier (if available)
        details: Arbitrary contextual dictionary (sanitized of passwords/secrets)
        trace_id: Correlation trace identifier
    """
    sanitized_details = (details or {}).copy()
    # Mask any sensitive keys that might have slipped into details
    for secret_key in ("password", "token", "secret", "access_token", "hashed_password"):
        if secret_key in sanitized_details:
            sanitized_details[secret_key] = "[REDACTED]"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": severity,
        "trace_id": trace_id or "N/A",
        "ip_address": ip_address or "unknown",
        "user_id": user_id or "anonymous",
        "details": sanitized_details,
    }

    try:
        audit_logger.info(json.dumps(entry))
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to write security audit log: {e}")
