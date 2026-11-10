import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


class FakeRedis:
    """Minimal async Redis double with a switchable outage."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.down = False

    def _check(self):
        if self.down:
            raise ConnectionError("redis down")

    async def get(self, k):
        self._check()
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self._check()
        self.store[k] = v

    async def delete(self, k):
        self._check()
        self.store.pop(k, None)

    async def ping(self):
        self._check()
        return True


def unreachable_llm() -> httpx.MockTransport:
    def handler(request):
        raise httpx.ConnectError("connection refused")

    return httpx.MockTransport(handler)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=("http://localhost:5173",),
        llm_enabled=True,
        groq_api_key="test-groq-key",
        gnani_api_key="",
    )
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def redis_fake():
    return FakeRedis()


@pytest.fixture
def client(tmp_path, redis_fake):
    app = create_app(make_settings(tmp_path), redis_client=redis_fake, llm_transport=unreachable_llm())
    with TestClient(app) as c:
        c.app_ref = app
        yield c
