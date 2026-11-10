"""Optional AI wording via Groq's OpenAI-compatible chat API.

The model only *words* an answer from verified facts. Its output is rejected
(and the rule-based answer used instead) if it contains numbers that are not in
the supplied facts, or claims a booking.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import Settings


class LLMUnavailable(Exception):
    pass


class LLMRejected(Exception):
    pass


SYSTEM = (
    "You are AutoSense AI, a used-car sales assistant for a demo dealership. "
    "Use ONLY the facts in the JSON the user provides. Never invent vehicles, prices, availability, "
    "features or bookings. Do not list prices or numbers that are not in the JSON. "
    "Reply in the same language/style as the customer (English, Hindi in Devanagari, or Hinglish in Latin script). "
    "Write 2-3 short sentences that introduce the verified options; the app shows full cards separately. "
    "Never say a test drive or booking is confirmed."
)

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BANNED = re.compile(r"\b(booked|booking (?:is )?confirmed|confirmed)\b|कन्फर्म|पक्की बुकिंग", re.I)


def _norm(n: str) -> str:
    return n.replace(",", "").rstrip(".")


def allowed_numbers(facts: dict[str, Any], user_message: str) -> set[str]:
    blob = json.dumps(facts, ensure_ascii=False) + " " + user_message
    return {_norm(n) for n in _NUM.findall(blob)}


def validate(text: str, facts: dict[str, Any], user_message: str) -> str:
    text = text.strip()
    if not text:
        raise LLMRejected("empty response")
    if _BANNED.search(text):
        raise LLMRejected("claims a booking/confirmation")
    allowed = allowed_numbers(facts, user_message)
    for n in _NUM.findall(text):
        v = _norm(n)
        if v in allowed:
            continue
        if re.fullmatch(r"\d{1,2}", v) and int(v) <= 10:  # counts like "3 options"
            continue
        raise LLMRejected(f"unverified number in output: {n}")
    return text


async def explain(settings: Settings, facts: dict[str, Any], user_message: str,
                  transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Ask Groq (OpenAI-compatible chat completions) to word a short intro from verified facts."""
    if not settings.llm_enabled:
        raise LLMUnavailable("AI wording disabled by configuration")
    if not settings.groq_api_key:
        raise LLMUnavailable("AI wording not configured (no GROQ_API_KEY)")
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Customer said: {user_message}\n\nVerified facts (JSON):\n"
                                         f"{json.dumps(facts, ensure_ascii=False)}"},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout, connect=5.0), transport=transport
        ) as client:
            r = await client.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers)
        if r.status_code == 429:
            raise LLMUnavailable("AI service rate-limited, try again shortly")
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"] or ""
    except LLMUnavailable:
        raise
    except httpx.HTTPStatusError as exc:
        raise LLMUnavailable(f"AI service unavailable (HTTP {exc.response.status_code})") from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise LLMUnavailable(f"AI service unavailable ({type(exc).__name__})") from exc
    return validate(content, facts, user_message)
