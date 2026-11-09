"""Cache-aside for individual vehicle details only.

Never used for chat responses or filtered search lists. Redis failures degrade
to PostgreSQL; counters are real (in-process) counts of what happened.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

log = logging.getLogger("autosense.cache")


class VehicleCache:
    def __init__(self, client: Any | None, ttl_seconds: int = 30):
        self.client = client
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
        self.errors = 0
        self.redis_ok: bool | None = None

    @staticmethod
    def key(vehicle_id: str) -> str:
        return f"vehicle:{vehicle_id}"

    async def get_or_load(
        self, vehicle_id: str, loader: Callable[[], dict[str, Any] | None]
    ) -> tuple[dict[str, Any] | None, str]:
        """Returns (value, cache_state) where state is HIT, MISS or BYPASS (Redis down)."""
        k = self.key(vehicle_id)
        state = "MISS"
        if self.client is not None:
            try:
                raw = await self.client.get(k)
                self.redis_ok = True
                if raw is not None:
                    self.hits += 1
                    return json.loads(raw), "HIT"
            except Exception as exc:  # Redis outage -> PostgreSQL
                self._fail("get", exc)
                state = "BYPASS"
        else:
            state = "BYPASS"
        value = loader()
        if state == "MISS":
            self.misses += 1
            if value is not None:
                try:
                    await self.client.set(k, json.dumps(value), ex=self.ttl)
                except Exception as exc:
                    self._fail("set", exc)
        return value, state

    async def invalidate(self, vehicle_id: str) -> bool:
        if self.client is None:
            return False
        try:
            await self.client.delete(self.key(vehicle_id))
            self.invalidations += 1
            self.redis_ok = True
            return True
        except Exception as exc:
            self._fail("delete", exc)
            return False

    async def ping(self) -> bool:
        if self.client is None:
            self.redis_ok = False
            return False
        try:
            await self.client.ping()
            self.redis_ok = True
        except Exception:
            self.redis_ok = False
        return bool(self.redis_ok)

    def _fail(self, op: str, exc: Exception) -> None:
        self.errors += 1
        self.redis_ok = False
        log.warning("redis %s failed, falling back to PostgreSQL: %s", op, exc)

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "errors": self.errors,
            "ttl_seconds": self.ttl,
            "redis_ok": self.redis_ok,
        }
