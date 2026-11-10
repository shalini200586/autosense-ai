import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import FakeRedis, make_settings, unreachable_llm


def _client(tmp_path, handler, key="test-key"):
    s = make_settings(tmp_path, gnani_api_key=key)
    app = create_app(s, redis_client=FakeRedis(), llm_transport=unreachable_llm(),
                     gnani_transport=httpx.MockTransport(handler))
    return TestClient(app)


def test_voice_setup_required_without_key(client):
    r = client.post("/api/voice/transcribe", files={"audio": ("a.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "voice_setup_required"
    r = client.post("/api/voice/synthesize", json={"text": "hello", "language": "en"})
    assert r.status_code == 503
    assert client.get("/api/health").json()["voice_configured"] is False
    assert client.post("/api/chat", json={"message": "automatic SUV 12 lakh"}).status_code == 200


def test_stt_request_format_and_response(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-api-key-id")
        seen["ctype"] = req.headers["content-type"]
        body = req.content
        seen["has_audio"] = b'name="audio_file"' in body
        seen["model"] = b"prisma-v3.0" in body
        seen["lang"] = b"hi-IN,en-IN" in body
        return httpx.Response(200, json={"success": True, "transcript": "मुझे 12 लाख के अंदर ऑटोमैटिक SUV चाहिए",
                                         "model": "prisma-v3.0", "detected_language_code": "hi-IN"})

    with _client(tmp_path, handler) as c:
        r = c.post("/api/voice/transcribe", files={"audio": ("speech.wav", b"RIFFfake", "audio/wav")})
    assert r.status_code == 200
    assert r.json()["transcript"].startswith("मुझे 12 लाख")
    assert seen["url"] == "https://api.vachana.ai/stt/v3" and seen["key"] == "test-key"
    assert seen["ctype"].startswith("multipart/form-data")
    assert seen["has_audio"] and seen["model"] and seen["lang"]


def test_stt_gnani_error_surfaces_cleanly(tmp_path):
    def handler(req):
        return httpx.Response(400, json={"success": False, "error": {
            "type": "MAX_AUDIO_DURATION_EXCEEDED", "message": "Audio duration exceeds maximum allowed duration of 30 seconds"}})

    with _client(tmp_path, handler) as c:
        r = c.post("/api/voice/transcribe", files={"audio": ("a.wav", b"RIFFfake", "audio/wav")})
        assert r.status_code == 502 and "30 seconds" in r.json()["detail"]["message"]
        assert c.post("/api/chat", json={"message": "hello"}).status_code == 200  # chat unaffected


def test_stt_network_failure(tmp_path):
    def handler(req):
        raise httpx.ConnectError("boom")

    with _client(tmp_path, handler) as c:
        r = c.post("/api/voice/transcribe", files={"audio": ("a.wav", b"RIFFfake", "audio/wav")})
        assert r.status_code == 502 and "Could not reach" in r.json()["detail"]["message"]


def test_tts_request_format(tmp_path):
    import json

    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-api-key-id")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=b"RIFFwavdata", headers={"content-type": "audio/wav"})

    with _client(tmp_path, handler) as c:
        r = c.post("/api/voice/synthesize", json={"text": "नमस्ते", "language": "hi"})
        assert r.status_code == 200 and r.content == b"RIFFwavdata" and r.headers["content-type"] == "audio/wav"
        c.post("/api/voice/synthesize", json={"text": "Hello", "language": "en"})
        c.post("/api/voice/synthesize", json={"text": "Aapke liye", "language": "hinglish"})
    assert seen["url"] == "https://api.vachana.ai/api/v1/tts/inference" and seen["key"] == "test-key"
    b = seen["body"]  # last call = hinglish
    assert b["model"] == "timbre-v2.5" and b["language"] == "hi-en" and b["voice"] == "Nalini"
    assert b["audio_config"]["container"] == "wav" and b["speed"] == 1.0


def test_tts_error(tmp_path):
    def handler(req):
        return httpx.Response(400, json={"success": False, "message": "voice not available", "status_code": 400})

    with _client(tmp_path, handler) as c:
        r = c.post("/api/voice/synthesize", json={"text": "hi", "language": "en"})
        assert r.status_code == 502 and "voice not available" in r.json()["detail"]["message"]


def test_spyne_profile_disables_voice_and_hides_vendor(tmp_path):
    s = make_settings(tmp_path, gnani_api_key="k", demo_profile="spyne")
    app = create_app(s, redis_client=FakeRedis(), llm_transport=unreachable_llm(),
                     gnani_transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"transcript": "x"})))
    with TestClient(app) as c:
        health = c.get("/api/health").json()
        assert health["profile"] == "spyne" and health["voice_enabled"] is False and health["voice_configured"] is False
        assert c.post("/api/voice/synthesize", json={"text": "hi", "language": "en"}).status_code == 404
        r = c.post("/api/voice/transcribe", files={"audio": ("a.wav", b"RIFF", "audio/wav")})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "voice_disabled"
        for path in ("/api/health", "/api/diagnostics"):
            assert "gnani" not in c.get(path).text.lower()
        assert c.post("/api/chat", json={"message": "automatic SUV 12 lakh"}).status_code == 200


def test_gnani_profile_is_default(client):
    h = client.get("/api/health").json()
    assert h["profile"] == "gnani" and h["voice_enabled"] is True


def test_api_key_never_in_responses(tmp_path):
    with _client(tmp_path, lambda req: httpx.Response(200, json={"transcript": "x"}), key="SUPERSECRET") as c:
        for path in ("/api/health", "/api/diagnostics"):
            assert "SUPERSECRET" not in c.get(path).text


@pytest.mark.skipif(not os.getenv("GNANI_API_KEY"), reason="GNANI_API_KEY not set; live smoke test skipped")
def test_live_gnani_tts_then_stt_roundtrip(tmp_path):
    """Real API smoke test: synthesize a Hindi phrase with Timbre, then transcribe it with Prisma."""
    s = Settings.from_env()
    app = create_app(make_settings(tmp_path, gnani_api_key=s.gnani_api_key), redis_client=FakeRedis(),
                     llm_transport=unreachable_llm())
    with TestClient(app) as c:
        tts = c.post("/api/voice/synthesize", json={"text": "मुझे बारह लाख के अंदर ऑटोमैटिक एसयूवी चाहिए", "language": "hi"})
        assert tts.status_code == 200 and tts.content[:4] == b"RIFF"
        stt = c.post("/api/voice/transcribe", files={"audio": ("tts.wav", tts.content, "audio/wav")})
        assert stt.status_code == 200 and stt.json()["transcript"].strip()
