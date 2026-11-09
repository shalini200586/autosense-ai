"""Gnani Prisma (STT) and Timbre (TTS) REST clients.

Request formats follow the official docs at https://docs.gnani.ai :
  STT  POST https://api.vachana.ai/stt/v3                 multipart, header X-API-Key-ID
       fields: audio_file, model, language_code, format ; JSON response has `transcript`
  TTS  POST https://api.vachana.ai/api/v1/tts/inference   JSON, header X-API-Key-ID
       body: text, voice, model, language, speed, audio_config ; response is raw audio
Credentials stay server-side. Whether a given language/voice is enabled depends on
your Gnani account.
"""
from __future__ import annotations

import httpx

from .config import Settings

STT_MAX_BYTES = 8 * 1024 * 1024  # local guard; the API documents a 30 second limit, not a size
TTS_MAX_CHARS = 500
TTS_LANGUAGE = {"en": "en-IN", "hi": "hi-IN", "hinglish": "hi-en"}


class GnaniNotConfigured(Exception):
    pass


class GnaniError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.gnani_api_key:
        raise GnaniNotConfigured("GNANI_API_KEY is not set")
    return {"X-API-Key-ID": settings.gnani_api_key}


def _err_message(r: httpx.Response) -> str:
    try:
        body = r.json()
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(body.get("message") or body.get("detail") or body)[:300]
    except ValueError:
        return (r.text or r.reason_phrase)[:300]


async def transcribe(settings: Settings, audio: bytes, filename: str, content_type: str,
                     transport: httpx.AsyncBaseTransport | None = None) -> dict:
    headers = _headers(settings)
    data = {
        "model": settings.gnani_stt_model,
        "language_code": settings.gnani_stt_languages,
        "format": settings.gnani_stt_format,
    }
    files = {"audio_file": (filename, audio, content_type)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), transport=transport) as client:
            r = await client.post(settings.gnani_stt_url, headers=headers, data=data, files=files)
    except httpx.HTTPError as exc:
        raise GnaniError(f"Could not reach Gnani speech service ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise GnaniError(_err_message(r), r.status_code)
    body = r.json()
    if body.get("success") is False:
        raise GnaniError(_err_message(r), r.status_code)
    return {"transcript": body.get("transcript", ""), "detected_language_code": body.get("detected_language_code"),
            "model": body.get("model")}


async def synthesize(settings: Settings, text: str, language: str,
                     transport: httpx.AsyncBaseTransport | None = None) -> tuple[bytes, str]:
    headers = {**_headers(settings), "Content-Type": "application/json"}
    voice = settings.gnani_tts_voice_en if language == "en" else settings.gnani_tts_voice_hi
    body = {
        "text": text[:TTS_MAX_CHARS],
        "voice": voice,
        "model": settings.gnani_tts_model,
        "language": TTS_LANGUAGE[language],
        "speed": 1.0,
        "audio_config": {"sample_rate": 24000, "encoding": "linear_pcm", "container": "wav"},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), transport=transport) as client:
            r = await client.post(settings.gnani_tts_url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise GnaniError(f"Could not reach Gnani speech service ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise GnaniError(_err_message(r), r.status_code)
    return r.content, r.headers.get("content-type", "audio/wav")
