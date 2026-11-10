from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above backend/) if present.
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

# Behind a TLS-inspecting corporate proxy? Put a CA bundle (public CAs + your proxy's root) at
# certs/ca-bundle.pem and it is used automatically for outbound HTTPS. Verification stays ON.
_bundle = _ROOT / "certs" / "ca-bundle.pem"
if _bundle.is_file():
    os.environ.setdefault("SSL_CERT_FILE", str(_bundle))


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://autosense:autosense@localhost:5432/autosense"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:8090")
    cache_ttl_seconds: int = 30
    # Optional AI wording via Groq's OpenAI-compatible API (https://console.groq.com). No key => rule-based answers.
    llm_enabled: bool = True
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"  # check console.groq.com for currently available models
    llm_timeout: float = 20.0
    groq_api_key: str = field(default="", repr=False)
    gnani_api_key: str = field(default="", repr=False)
    gnani_stt_url: str = "https://api.vachana.ai/stt/v3"
    gnani_tts_url: str = "https://api.vachana.ai/api/v1/tts/inference"
    gnani_stt_model: str = "prisma-v3.0"
    gnani_stt_languages: str = "hi-IN,en-IN"
    gnani_stt_format: str = "verbatim"
    gnani_tts_model: str = "timbre-v2.5"
    gnani_tts_voice_hi: str = "Nalini"
    gnani_tts_voice_en: str = "Kaveri"
    admin_token: str = field(default="", repr=False)
    # "gnani": voice-first demo, Gnani Prisma/Timbre named on screen.
    # "spyne": inventory-sync demo; voice disabled and no Gnani mention anywhere in the UI/API.
    demo_profile: str = "gnani"

    @classmethod
    def from_env(cls) -> "Settings":
        g = os.getenv
        d = cls()
        return cls(
            database_url=g("DATABASE_URL", d.database_url),
            redis_url=g("REDIS_URL", d.redis_url),
            cors_origins=tuple(
                o.strip() for o in g("CORS_ORIGINS", ",".join(d.cors_origins)).split(",") if o.strip()
            ),
            cache_ttl_seconds=int(g("CACHE_TTL_SECONDS", d.cache_ttl_seconds)),
            llm_enabled=_bool("LLM_ENABLED", d.llm_enabled),
            llm_base_url=g("LLM_BASE_URL", d.llm_base_url).rstrip("/"),
            llm_model=g("LLM_MODEL", d.llm_model),
            llm_timeout=float(g("LLM_TIMEOUT", d.llm_timeout)),
            groq_api_key=g("GROQ_API_KEY", ""),
            gnani_api_key=g("GNANI_API_KEY", ""),
            gnani_stt_url=g("GNANI_STT_URL", d.gnani_stt_url),
            gnani_tts_url=g("GNANI_TTS_URL", d.gnani_tts_url),
            gnani_stt_model=g("GNANI_STT_MODEL", d.gnani_stt_model),
            gnani_stt_languages=g("GNANI_STT_LANGUAGES", d.gnani_stt_languages),
            gnani_stt_format=g("GNANI_STT_FORMAT", d.gnani_stt_format),
            gnani_tts_model=g("GNANI_TTS_MODEL", d.gnani_tts_model),
            gnani_tts_voice_hi=g("GNANI_TTS_VOICE_HI", d.gnani_tts_voice_hi),
            gnani_tts_voice_en=g("GNANI_TTS_VOICE_EN", d.gnani_tts_voice_en),
            admin_token=g("ADMIN_TOKEN", ""),
            demo_profile=g("DEMO_PROFILE", d.demo_profile).strip().lower(),
        )

    @property
    def voice_enabled(self) -> bool:
        return self.demo_profile != "spyne"
