"""AI Assistant prompt-injection firewall, daily quota budgeting & secret leak sanitizer."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

MAX_CHAT_PROMPT_CHARS = 1200

DAILY_QUOTA_BY_TIER = {
    "FREE": 15,
    "PRO": 200,
    "ADMIN": 500,
}

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)", re.I),
    re.compile(r"(reveal|print|dump|show|output|leak)\s+(your\s+|the\s+)?(system\s*prompt|instructions?|\.env|env\s*vars?|secret[_\s]*key|api[_\s]*key|groq[_\s]*api[_\s]*key|fyers)", re.I),
    re.compile(r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|###\s*(system|developer)\s*:?)", re.I),
    re.compile(r"(bypass\s+(security|guardrails?|filters?)|enter\s+developer\s+mode|jailbreak)", re.I),
]

_SECRET_REDACTION_PATTERNS = [
    (re.compile(r"\bgsk_[A-Za-z0-9]{12,}\b"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(SECRET_KEY|GROQ_API_KEY|FYERS_SECRET_KEY|DATABASE_URL|REDIS_PASSWORD)\s*=\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"<\s*/?\s*script[^>]*>", re.I), ""),
]

# Local per-process quota fallback when Redis is unavailable
_LOCAL_AI_QUOTA: Dict[str, Tuple[int, float]] = {}


@dataclass(frozen=True)
class PromptGuardResult:
    allowed: bool
    sanitized_message: str
    reason: Optional[str] = None


def inspect_ai_prompt(message: str) -> PromptGuardResult:
    """Validate chat query bounds and block prompt-injection or credential exfiltration attempts."""
    raw = (message or "").strip()
    if not raw:
        return PromptGuardResult(allowed=False, sanitized_message="", reason="empty_message")
    if len(raw) > MAX_CHAT_PROMPT_CHARS:
        return PromptGuardResult(
            allowed=False,
            sanitized_message="",
            reason=f"Query exceeds maximum {MAX_CHAT_PROMPT_CHARS} character limit.",
        )

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(raw):
            return PromptGuardResult(
                allowed=False,
                sanitized_message="",
                reason="Prompt-injection or secret-extraction pattern rejected.",
            )

    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    return PromptGuardResult(allowed=True, sanitized_message=cleaned)


def wrap_untrusted_user_prompt(clean_message: str, context: dict) -> str:
    """Wrap user input inside explicit untrusted delimiters separated from verified context."""
    return (
        "<user_query>\n"
        f"{clean_message}\n"
        "</user_query>\n\n"
        "<verified_python_context>\n"
        f"{context}\n"
        "</verified_python_context>"
    )


def sanitize_ai_output(content: str) -> str:
    """Strip accidental key/JWT patterns and unsafe script tags from generated AI output."""
    text = str(content or "")
    for pattern, replacement in _SECRET_REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


async def check_and_consume_ai_quota(
    user_id: Optional[str],
    tier: str = "PRO",
    is_admin: bool = False,
) -> Dict[str, int | bool]:
    """
    Enforce daily per-user AI chat request cap via atomic Redis counter (with safe memory fallback).
    Prevents runaway automation or compromised accounts from exhausting upstream LLM budgets.
    """
    norm_tier = "ADMIN" if is_admin else str(tier or "PRO").upper()
    limit = DAILY_QUOTA_BY_TIER.get(norm_tier, DAILY_QUOTA_BY_TIER["PRO"])
    if not user_id:
        return {"allowed": True, "used": 0, "limit": limit, "remaining": limit}

    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    redis_key = f"ai_quota:{user_id}:{day_key}"

    try:
        from backend.core.cache import get_redis

        async def _incr_redis():
            r = await get_redis()
            if r is None:
                return None
            cnt = await r.incr(redis_key)
            if int(cnt) == 1:
                await r.expire(redis_key, 86400)
            return int(cnt)

        used = await asyncio.wait_for(_incr_redis(), timeout=0.08)
        if used is not None:
            return {
                "allowed": used <= limit,
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used),
            }
    except Exception:
        pass

    now = time.time()
    prev_count, reset_ts = _LOCAL_AI_QUOTA.get(redis_key, (0, now + 86400))
    if now > reset_ts:
        prev_count = 0
        reset_ts = now + 86400
    next_count = prev_count + 1
    _LOCAL_AI_QUOTA[redis_key] = (next_count, reset_ts)
    return {
        "allowed": next_count <= limit,
        "used": next_count,
        "limit": limit,
        "remaining": max(0, limit - next_count),
    }
