"""Live voice round trip through a RUNNING stack: Timbre TTS -> Prisma STT -> chat on the transcript.

    backend/.venv/Scripts/python scripts/voice_check.py [base_url] ["phrase"]
Requires GNANI_API_KEY configured in the backend. Makes real Gnani API calls.
"""
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"
PHRASE = sys.argv[2] if len(sys.argv) > 2 else "मुझे बारह लाख के अंदर ऑटोमैटिक एसयूवी चाहिए"

with httpx.Client(timeout=120) as c:
    tts = c.post(f"{BASE}/api/voice/synthesize", json={"text": PHRASE, "language": "hi"})
    print("TTS  :", tts.status_code, tts.headers.get("content-type"), len(tts.content), "bytes", tts.content[:4])
    tts.raise_for_status()
    stt = c.post(f"{BASE}/api/voice/transcribe", files={"audio": ("speech.wav", tts.content, "audio/wav")})
    print("STT  :", stt.status_code, stt.json())
    stt.raise_for_status()
    text = stt.json()["transcript"]
    chat = c.post(f"{BASE}/api/chat", json={"message": text}).json()
    print("CHAT :", chat["intent"], [v["id"] for v in chat["vehicles"]], "| source:", chat["source"])
