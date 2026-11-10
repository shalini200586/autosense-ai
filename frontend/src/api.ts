export type Vehicle = {
  id: string; make: string; model: string; variant: string; year: number; fuel: string;
  transmission: string; body_type: string; mileage_km: number; price_inr: number;
  status: "available" | "sold"; is_demo: boolean; version: number; created_at: string; updated_at: string;
};
export type Counts = { total: number; available: number; sold: number };
export type ChatResponse = {
  reply: string; language: "en" | "hi" | "hinglish"; intent: string; vehicles: Vehicle[]; alternatives: Vehicle[];
  source: "llm" | "fallback"; fallback_reason: string | null; checked_at: string; test_drive_request_id: number | null;
};
export type InventoryEvent = {
  type: string; vehicle_id?: string; label?: string; at: string;
  changes?: Record<string, { from: string | number; to: string | number }>;
};
export type Diagnostics = {
  cache: { hits: number; misses: number; invalidations: number; errors: number; ttl_seconds: number; redis_ok: boolean | null };
  inventory: Counts; websocket_clients: number; events: InventoryEvent[];
  llm: { enabled: boolean; model: string }; voice_configured: boolean; admin_token_required: boolean;
};
export type Health = { status: string; database: boolean; redis: boolean; voice_configured: boolean; llm_enabled: boolean };

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try { r = await fetch(url, init); } catch { throw new ApiError("Cannot reach the server. Is the backend running?", 0, "offline"); }
  if (!r.ok) {
    let msg = r.statusText, code: string | undefined;
    try {
      const j = await r.json();
      const d = j.detail;
      if (typeof d === "string") msg = d;
      else if (d?.message) { msg = d.message; code = d.code; }
      else if (Array.isArray(d)) msg = d.map((e: { msg: string }) => e.msg).join("; ");
    } catch { /* non-JSON error */ }
    throw new ApiError(msg, r.status, code);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  health: () => req<Health>("/api/health"),
  vehicles: (p: { q?: string; status?: string; type?: string }) => {
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]);
    return req<{ vehicles: Vehicle[]; counts: Counts; as_of: string }>(`/api/vehicles?${qs}`);
  },
  patch: (id: string, body: { price_inr?: number; status?: string }, token?: string) =>
    req<Vehicle>(`/api/vehicles/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(token ? { "X-Admin-Token": token } : {}) },
      body: JSON.stringify(body),
    }),
  diagnostics: () => req<Diagnostics>("/api/diagnostics"),
  chat: (message: string, last_vehicle_ids: string[]) => req<ChatResponse>("/api/chat", json({ message, last_vehicle_ids })),
  transcribe: async (wav: Blob) => {
    const fd = new FormData();
    fd.append("audio", wav, "speech.wav");
    return req<{ transcript: string; detected_language_code?: string }>("/api/voice/transcribe", { method: "POST", body: fd });
  },
  synthesize: async (text: string, language: string): Promise<Blob> => {
    let r: Response;
    try { r = await fetch("/api/voice/synthesize", json({ text, language })); } catch { throw new ApiError("Cannot reach the server.", 0, "offline"); }
    if (!r.ok) {
      let msg = "Speech playback failed", code: string | undefined;
      try { const d = (await r.json()).detail; msg = d?.message ?? msg; code = d?.code; } catch { /* ignore */ }
      throw new ApiError(msg, r.status, code);
    }
    return r.blob();
  },
};

export const inr = (n: number) => "₹" + n.toLocaleString("en-IN");
export const lakh = (n: number) => `₹${(n / 100000).toFixed(2).replace(/\.?0+$/, "")} lakh`;
export const timeAgo = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
