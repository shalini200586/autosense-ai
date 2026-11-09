import { useEffect, useRef, useState } from "react";
import type { InventoryEvent } from "./api";

export type SocketState = "connecting" | "open" | "closed";

/** Connects to /ws/inventory, auto-reconnects with backoff, and calls onReconnect after every re-open
 *  so the caller can refetch current inventory. */
export function useInventorySocket(onEvent: (e: InventoryEvent) => void, onResync: () => void) {
  const [state, setState] = useState<SocketState>("connecting");
  const evRef = useRef(onEvent);
  const syncRef = useRef(onResync);
  evRef.current = onEvent;
  syncRef.current = onResync;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let hadConnection = false;
    let stopped = false;

    const connect = () => {
      setState("connecting");
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/inventory`);
      ws.onopen = () => {
        attempt = 0;
        setState("open");
        if (hadConnection) syncRef.current(); // reconnected: refetch current inventory
        hadConnection = true;
      };
      ws.onmessage = (m) => {
        try {
          const e = JSON.parse(m.data) as InventoryEvent;
          if (e.type !== "hello") evRef.current(e);
        } catch { /* ignore malformed */ }
      };
      ws.onclose = () => {
        setState("closed");
        if (stopped) return;
        timer = window.setTimeout(connect, Math.min(10000, 1000 * 2 ** attempt++));
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    const ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 25000);
    return () => { stopped = true; clearTimeout(timer); clearInterval(ping); ws?.close(); };
  }, []);

  return state;
}
