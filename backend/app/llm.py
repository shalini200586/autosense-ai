"""Optional Ollama explainer.

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


class OllamaUnavailable(Exception):
    pass


class OllamaRejected(Exception):
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
        raise OllamaRejected("empty response")
    if _BANNED.search(text):
        raise OllamaRejected("claims a booking/confirmation")
    allowed = allowed_numbers(facts, user_message)
    for n in _NUM.findall(text):
        v = _norm(n)
        if v in allowed:
            continue
        if re.fullmatch(r"\d{1,2}", v) and int(v) <= 10:  # counts like "3 options"
            continue
        raise OllamaRejected(f"unverified number in output: {n}")
    return text


async def warm_up(settings: Settings) -> None:
    """Best-effort: load the model into memory so the first customer question isn't a cold start."""
    if not settings.ollama_enabled:
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=2.0)) as client:
            await client.post(f"{settings.ollama_url}/api/chat", json={
                "model": settings.ollama_model, "stream": False, "keep_alive": "30m",
                "options": {"num_predict": 1}, "messages": [{"role": "user", "content": "hi"}]})
    except httpx.HTTPError:
        pass  # Ollama not running: chat will use the labelled rule-based fallback


async def explain(settings: Settings, facts: dict[str, Any], user_message: str,
                  transport: httpx.AsyncBaseTransport | None = None) -> str:
    if not settings.ollama_enabled:
        raise OllamaUnavailable("Ollama disabled by configuration")
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_predict": 200},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Customer said: {user_message}\n\nVerified facts (JSON):\n"
                                         f"{json.dumps(facts, ensure_ascii=False)}"},
        ],
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ollama_timeout, connect=2.0), transport=transport
        ) as client:
            r = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
            r.raise_for_status()
            content = r.json()["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise OllamaUnavailable(f"Ollama unavailable ({type(exc).__name__})") from exc
    return validate(content, facts, user_message)
