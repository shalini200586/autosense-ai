from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from . import gnani, llm
from .assistant import handle_chat
from .cache import VehicleCache
from .config import Settings
from .db import Base, make_engine, make_session_factory
from .events import InventoryHub
from .models import Vehicle, utcnow
from .schemas import ChatRequest, ChatResponse, SynthesizeRequest, VehicleUpdate
from .seed import seed_if_empty
from .serialize import iso, vehicle_to_dict

log = logging.getLogger("autosense")


def _init_db(engine, session_factory, retries: int = 15) -> None:
    last: Exception | None = None
    for _ in range(retries):
        try:
            Base.metadata.create_all(engine)
            with session_factory() as s:
                seed_if_empty(s)
            return
        except Exception as exc:  # DB may still be starting
            last = exc
            import time
            time.sleep(1)
    raise RuntimeError(f"Database not reachable: {last}")


def create_app(
    settings: Settings | None = None,
    redis_client: Any | None = "auto",  # type: ignore[assignment]
    ollama_transport: httpx.AsyncBaseTransport | None = None,
    gnani_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    SessionLocal = make_session_factory(engine)

    if redis_client == "auto":
        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(
                settings.redis_url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True
            )
        except Exception:
            redis_client = None

    cache = VehicleCache(redis_client, settings.cache_ttl_seconds)
    hub = InventoryHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.get_running_loop().run_in_executor(None, _init_db, engine, SessionLocal)
        await cache.ping()
        warm = asyncio.create_task(llm.warm_up(settings)) if ollama_transport is None else None
        yield
        if warm:
            warm.cancel()
        if redis_client is not None and hasattr(redis_client, "aclose"):
            try:
                await redis_client.aclose()
            except Exception:
                pass

    app = FastAPI(title="AutoSense AI", version="1.0.0", lifespan=lifespan)
    app.state.settings, app.state.cache, app.state.hub = settings, cache, hub
    app.state.session_factory, app.state.engine = SessionLocal, engine

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )

    def get_session():
        with SessionLocal() as s:
            yield s

    def counts(s: Session) -> dict[str, int]:
        rows = dict(s.execute(select(Vehicle.status, func.count()).group_by(Vehicle.status)).all())
        return {"total": sum(rows.values()), "available": rows.get("available", 0), "sold": rows.get("sold", 0)}

    # ---- health / diagnostics ---------------------------------------------------
    @app.get("/api/health")
    async def health(s: Session = Depends(get_session)):
        try:
            s.execute(text("select 1"))
            db_ok = True
        except Exception:
            db_ok = False
        redis_ok = await cache.ping()
        return {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "redis": redis_ok,
            "voice_configured": bool(settings.gnani_api_key),
            "ollama_enabled": settings.ollama_enabled,
            "time": iso(datetime.now(timezone.utc)),
        }

    @app.get("/api/diagnostics")
    async def diagnostics(s: Session = Depends(get_session)):
        redis_ok = await cache.ping()
        return {
            "cache": {**cache.stats(), "redis_ok": redis_ok},
            "inventory": counts(s),
            "websocket_clients": len(hub.connections),
            "events": list(hub.log)[:30],
            "ollama": {"enabled": settings.ollama_enabled, "model": settings.ollama_model},
            "voice_configured": bool(settings.gnani_api_key),
            "admin_token_required": bool(settings.admin_token),
        }

    # ---- inventory -----------------------------------------------------------------
    @app.get("/api/vehicles")
    async def list_vehicles(
        q: str | None = Query(default=None, max_length=60),
        status: str | None = Query(default=None, pattern="^(available|sold)$"),
        type: str | None = Query(default=None, max_length=20),
        s: Session = Depends(get_session),
    ):
        # Lists always come straight from PostgreSQL (never cached).
        stmt = select(Vehicle)
        if status:
            stmt = stmt.where(Vehicle.status == status)
        if type:
            stmt = stmt.where(func.lower(Vehicle.body_type) == type.lower())
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(
                func.lower(Vehicle.make).like(like), func.lower(Vehicle.model).like(like),
                func.lower(Vehicle.variant).like(like), func.lower(Vehicle.id).like(like)))
        rows = s.scalars(stmt.order_by(Vehicle.id)).all()
        return {"vehicles": [vehicle_to_dict(v) for v in rows], "counts": counts(s),
                "as_of": iso(datetime.now(timezone.utc))}

    @app.get("/api/vehicles/{vehicle_id}")
    async def get_vehicle(vehicle_id: str, response: Response, s: Session = Depends(get_session)):
        def load():
            v = s.get(Vehicle, vehicle_id)
            return vehicle_to_dict(v) if v else None

        value, state = await cache.get_or_load(vehicle_id, load)
        if value is None:
            raise HTTPException(404, "Vehicle not found")
        response.headers["X-Cache"] = state
        return value

    @app.patch("/api/vehicles/{vehicle_id}")
    async def update_vehicle(
        vehicle_id: str,
        body: VehicleUpdate,
        s: Session = Depends(get_session),
        x_admin_token: str | None = Header(default=None),
    ):
        if settings.admin_token and x_admin_token != settings.admin_token:
            raise HTTPException(401, "Admin token required")
        v = s.get(Vehicle, vehicle_id)
        if v is None:
            raise HTTPException(404, "Vehicle not found")
        if body.expected_version is not None and body.expected_version != v.version:
            raise HTTPException(409, f"Vehicle changed (current version {v.version})")
        changes: dict[str, Any] = {}
        if body.price_inr is not None and body.price_inr != v.price_inr:
            changes["price_inr"] = {"from": v.price_inr, "to": body.price_inr}
            v.price_inr = body.price_inr
        if body.status is not None and body.status != v.status:
            changes["status"] = {"from": v.status, "to": body.status}
            v.status = body.status
        if not changes:
            return vehicle_to_dict(v)
        v.version += 1
        v.updated_at = utcnow()
        s.commit()  # 1. PostgreSQL commit
        await cache.invalidate(vehicle_id)  # 2. Redis invalidation
        event = {  # 3. WebSocket broadcast
            "type": "inventory_changed", "vehicle_id": vehicle_id, "changes": changes,
            "version": v.version, "label": f"{v.make} {v.model}", "at": iso(v.updated_at),
        }
        await hub.broadcast(event)
        return vehicle_to_dict(v)

    # ---- chat ----------------------------------------------------------------------
    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, s: Session = Depends(get_session)):
        try:
            return await handle_chat(body, s, settings, ollama_transport)
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("chat failed")
            raise HTTPException(503, "Inventory is temporarily unavailable. Please try again.") from exc

    # ---- voice (Gnani) ---------------------------------------------------------------
    @app.post("/api/voice/transcribe")
    async def transcribe(audio: UploadFile = File(...)):
        if not settings.gnani_api_key:
            raise HTTPException(503, {"code": "voice_setup_required", "message": "Voice setup required"})
        data = await audio.read(gnani.STT_MAX_BYTES + 1)
        if not data:
            raise HTTPException(400, {"code": "empty_audio", "message": "No audio received"})
        if len(data) > gnani.STT_MAX_BYTES:
            raise HTTPException(413, {"code": "audio_too_large", "message": "Audio is too large"})
        try:
            return await gnani.transcribe(
                settings, data, audio.filename or "speech.wav", audio.content_type or "audio/wav", gnani_transport)
        except gnani.GnaniError as exc:
            raise HTTPException(502, {"code": "gnani_error", "message": f"Gnani Prisma: {exc.message}"}) from exc

    @app.post("/api/voice/synthesize")
    async def synthesize(body: SynthesizeRequest):
        if not settings.gnani_api_key:
            raise HTTPException(503, {"code": "voice_setup_required", "message": "Voice setup required"})
        try:
            audio, ctype = await gnani.synthesize(settings, body.text, body.language, gnani_transport)
        except gnani.GnaniError as exc:
            raise HTTPException(502, {"code": "gnani_error", "message": f"Gnani Timbre: {exc.message}"}) from exc
        return Response(content=audio, media_type=ctype)

    # ---- websocket -------------------------------------------------------------------
    @app.websocket("/ws/inventory")
    async def ws_inventory(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            await ws.close(code=1008)
            return
        await hub.connect(ws)
        try:
            await ws.send_json({"type": "hello", "at": iso(datetime.now(timezone.utc))})
            while True:
                await ws.receive_text()  # keep-alive; clients send "ping"
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(ws)

    return app


def get_app() -> FastAPI:  # uvicorn --factory app.main:get_app
    return create_app()
