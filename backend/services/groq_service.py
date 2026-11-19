"""Groq AI Service — Ultra-Fast LLM Inference Client with Strict Token Budgeting.

Uses Groq's OpenAI-compatible completions API endpoint with async non-blocking HTTP requests.
Enforces precision response formatting and low latency for financial chatbot interactions.
"""

import time
import logging
from typing import Dict, Any, Optional
import httpx

from backend.core.config import Settings

logger = logging.getLogger(__name__)
settings = Settings()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqService:
    """Asynchronous Groq AI client for real-time market chatbot completions."""

    def __init__(self):
        self._api_url = GROQ_API_URL

    def is_configured(self) -> bool:
        """Check whether a valid Groq API key is present."""
        key = settings.GROQ_API_KEY
        return bool(key and len(key.strip()) > 8 and not key.startswith("change-me"))

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate high-speed chat completion via Groq AI.
        
        Returns:
            dict with 'content', 'model', 'tokens_used', 'latency_ms' or None on failure/missing key.
        """
        if not self.is_configured():
            logger.debug("[Groq] GROQ_API_KEY not configured or empty. Skipping Groq inference.")
            return None

        effective_max_tokens = max_tokens or settings.GROQ_MAX_TOKENS
        effective_temp = temperature if temperature is not None else settings.GROQ_TEMPERATURE

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY.strip()}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": effective_max_tokens,
            "temperature": effective_temp,
            "top_p": 0.9,
            "stream": False
        }

        start_time = time.perf_counter()
        timeout = httpx.Timeout(settings.GROQ_TIMEOUT_SECONDS, connect=3.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._api_url, json=payload, headers=headers)
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "").strip()
                        usage = data.get("usage", {})
                        total_tokens = usage.get("total_tokens", 0)
                        logger.info(f"⚡ [Groq AI] Generated response in {latency_ms}ms ({total_tokens} tokens) via {settings.GROQ_MODEL}")
                        return {
                            "content": content,
                            "model": settings.GROQ_MODEL,
                            "tokens_used": total_tokens,
                            "latency_ms": latency_ms,
                            "success": True
                        }
                elif response.status_code == 429:
                    logger.warning(f"⚠️ [Groq AI] Rate limit reached (HTTP 429). Falling back to deterministic RAG engine.")
                    return None
                elif response.status_code == 401:
                    logger.error(f"❌ [Groq AI] Authentication error (HTTP 401). Please check GROQ_API_KEY in .env.")
                    return None
                else:
                    logger.warning(f"⚠️ [Groq AI] Unexpected status {response.status_code}: {response.text[:120]}")
                    return None

        except httpx.TimeoutException:
            logger.warning(f"⚠️ [Groq AI] Request timed out after {settings.GROQ_TIMEOUT_SECONDS}s. Falling back to deterministic RAG.")
            return None
        except Exception as e:
            logger.error(f"❌ [Groq AI] Client error: {e}")
            return None


groq_service = GroqService()
