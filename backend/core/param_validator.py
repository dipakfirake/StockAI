"""
Input Validation and Parameter Sanitization Utility for Financial Endpoints.

Defends against:
- Path Traversal (e.g. ../../)
- Code Injection / SQL Injection fragments
- Cross-Site Scripting (XSS)
- Maliciously long or malformed symbol parameters
"""

import re
from fastapi import HTTPException, status

# Whitelist regex for stock symbols:
# Allows uppercase/lowercase letters, digits, '.', '-', ':', and '^' (e.g. RELIANCE.NS, ^NSEI, TATAMOTORS, 500325.BO)
# Length between 1 and 30 characters.
SYMBOL_REGEX = re.compile(r"^[A-Za-z0-9\.\-\:\^]{1,30}$")

# Friendly aliases for major indices to enable clean URLs (e.g. /chart/NIFTY50 -> ^NSEI)
INDEX_ALIASES = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY-50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
    "NIFTY-BANK": "^NSEBANK",
    "SENSEX": "^BSESN",
    "BSE-SENSEX": "^BSESN",
    "INDIAVIX": "^INDIAVIX",
    "VIX": "^INDIAVIX",
}

VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mo"}


def sanitize_symbol(raw_symbol: str) -> str:
    """
    Validate, sanitize, and normalize a stock or index symbol.
    Raises HTTPException(400) if symbol contains invalid characters or exceeds bounds.
    """
    if not raw_symbol or not isinstance(raw_symbol, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock symbol must be a non-empty string.",
        )

    # Strip whitespace and URL-decode artifacts
    cleaned = raw_symbol.strip().upper()

    # Map friendly index aliases if used
    if cleaned in INDEX_ALIASES:
        return INDEX_ALIASES[cleaned]

    # Validate against strict regex whitelist
    if not SYMBOL_REGEX.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid symbol format: '{raw_symbol}'. "
                "Symbols must be between 1 and 30 characters and only contain "
                "letters, numbers, dots, hyphens, colons, or carets."
            ),
        )

    return cleaned


def validate_timeframe(tf: str) -> str:
    """Validate timeframe against allowed list."""
    cleaned = tf.strip().lower() if tf else "1d"
    if cleaned not in VALID_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe: '{tf}'. Allowed values: {sorted(list(VALID_TIMEFRAMES))}",
        )
    return cleaned
