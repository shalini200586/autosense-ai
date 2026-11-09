from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("autosense.events")


class InventoryHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self.log: deque[dict[str, Any]] = deque(maxlen=50)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> int:
        self.log.appendleft(event)
        sent = 0
        for ws in list(self.connections):
            try:
                await ws.send_json(event)
                sent += 1
            except Exception:
                self.connections.discard(ws)
        return sent
