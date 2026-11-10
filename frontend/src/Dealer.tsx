import { useCallback, useEffect, useRef, useState } from "react";
import { Database, Radio, Search } from "lucide-react";
import { api, ApiError, inr, timeAgo, type Counts, type Diagnostics, type InventoryEvent, type Vehicle } from "./api";
import { useInventorySocket } from "./useInventorySocket";

const TYPES = ["", "SUV", "Sedan", "Hatchback", "MPV"];

export default function Dealer() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [asOf, setAsOf] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [events, setEvents] = useState<InventoryEvent[]>([]);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState(sessionStorage.getItem("adminToken") ?? "");
  const filters = useRef({ q, status, type });
  filters.current = { q, status, type };

  const load = useCallback(async () => {
    try {
      const r = await api.vehicles(filters.current);
      setVehicles(r.vehicles); setCounts(r.counts); setAsOf(r.as_of); setError(null);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
    api.diagnostics().then(setDiag).catch(() => setDiag(null));
  }, []);

  useEffect(() => { const t = setTimeout(load, 150); return () => clearTimeout(t); }, [q, status, type, load]);

  const socket = useInventorySocket((e) => {
    setEvents((p) => [e, ...p].slice(0, 40));
    if (e.vehicle_id) { setFlash(e.vehicle_id); setTimeout(() => setFlash(null), 1500); }
    load();
  }, load);

  const update = async (id: string, body: { price_inr?: number; status?: string }) => {
    try { await api.patch(id, body, token || undefined); setError(null); await load(); }
    catch (e) { setError(e instanceof ApiError && e.status === 401 ? "Admin token required or incorrect." : (e as Error).message); load(); }
  };

  return (
    <div className="animate-rise space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inventory</h1>
          <p className="mt-1 text-sm text-mute">PostgreSQL is the source of truth. Changes commit, invalidate Redis, then notify every connected client.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-mute">
          <span className={`h-2 w-2 rounded-full ${socket === "open" ? "bg-emerald-500" : socket === "connecting" ? "bg-amber-400" : "bg-red-500"}`} />
          {socket === "open" ? "Live" : socket === "connecting" ? "Connecting…" : "Disconnected – retrying"}
          {asOf && <span>· as of {timeAgo(asOf)}</span>}
        </div>
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      <div className="grid grid-cols-3 gap-3">
        {[["Total", counts?.total], ["Available", counts?.available], ["Sold", counts?.sold]].map(([l, v]) => (
          <div key={l as string} className="rounded-xl border border-line bg-white px-4 py-3">
            <div className="text-xs text-mute">{l}</div>
            <div className="text-2xl font-semibold tabular-nums">{v ?? "–"}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="absolute left-3 top-2.5 text-neutral-400" />
          <input className="input pl-9" placeholder="Search make, model, variant or ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search inventory" />
        </div>
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option><option value="available">Available</option><option value="sold">Sold</option>
        </select>
        <select className="input w-auto" value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by type">
          {TYPES.map((t) => <option key={t} value={t}>{t || "All types"}</option>)}
        </select>
        {diag?.admin_token_required && (
          <input className="input w-44" type="password" placeholder="Admin token" value={token}
            onChange={(e) => { setToken(e.target.value); sessionStorage.setItem("adminToken", e.target.value); }} />
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-xs text-mute">
            <tr>{["ID", "Vehicle", "Specs", "Price (₹)", "Status", "Updated"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-4 py-8 text-center text-mute">Loading inventory…</td></tr>}
            {!loading && vehicles.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-mute">No vehicles match.</td></tr>}
            {vehicles.map((v) => <Row key={v.id} v={v} flash={flash === v.id} onUpdate={update} />)}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-xl border border-line bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Database size={15} /> Redis diagnostics</h2>
          {diag ? (
            <>
              <dl className="grid grid-cols-4 gap-2 text-center">
                {([["Hits", diag.cache.hits], ["Misses", diag.cache.misses], ["Invalidations", diag.cache.invalidations], ["Errors", diag.cache.errors]] as const).map(([l, v]) => (
                  <div key={l} className="rounded-lg bg-neutral-50 py-2"><dd className="text-lg font-semibold tabular-nums">{v}</dd><dt className="text-[11px] text-mute">{l}</dt></div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-mute">
                Redis: <b className={diag.cache.redis_ok ? "text-emerald-600" : "text-red-600"}>{diag.cache.redis_ok ? "connected" : "unavailable – using PostgreSQL"}</b>
                {" · "}vehicle-detail TTL {diag.cache.ttl_seconds}s · {diag.websocket_clients} live client(s). Lists and chat are never cached.
              </p>
            </>
          ) : <p className="text-sm text-mute">Diagnostics unavailable.</p>}
        </section>
        <section className="rounded-xl border border-line bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Radio size={15} /> Real-time event log</h2>
          <ul className="max-h-40 space-y-1.5 overflow-y-auto text-xs">
            {events.length === 0 && <li className="text-mute">Waiting for inventory changes…</li>}
            {events.map((e, i) => (
              <li key={i} className="flex gap-2"><span className="shrink-0 tabular-nums text-mute">{new Date(e.at).toLocaleTimeString("en-IN")}</span>
                <span><b>{e.label}</b> ({e.vehicle_id}) {Object.entries(e.changes ?? {}).map(([k, c]) => `${k}: ${c.from} → ${c.to}`).join(", ")}</span></li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Row({ v, flash, onUpdate }: { v: Vehicle; flash: boolean; onUpdate: (id: string, b: { price_inr?: number; status?: string }) => void }) {
  const [price, setPrice] = useState(String(v.price_inr));
  useEffect(() => setPrice(String(v.price_inr)), [v.price_inr, v.version]);
  const n = Number(price);
  const valid = Number.isInteger(n) && n > 0;
  const dirty = valid && n !== v.price_inr;
  return (
    <tr className={`border-b border-line last:border-0 ${flash ? "animate-flash" : ""}`}>
      <td className="px-4 py-2.5 font-mono text-xs text-mute">{v.id}</td>
      <td className="px-4 py-2.5"><div className="font-medium">{v.make} {v.model}</div><div className="text-xs text-mute">{v.variant} · {v.year}</div></td>
      <td className="px-4 py-2.5 text-xs text-mute">{v.body_type} · {v.fuel} · {v.transmission}<br />{v.mileage_km.toLocaleString("en-IN")} km</td>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-1.5">
          <input className={`input w-28 py-1 tabular-nums ${!valid ? "border-red-400" : ""}`} inputMode="numeric" value={price}
            aria-label={`Price for ${v.model}`} onChange={(e) => setPrice(e.target.value.replace(/[^\d]/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && dirty && onUpdate(v.id, { price_inr: n })} />
          {dirty && <button className="btn py-1" onClick={() => onUpdate(v.id, { price_inr: n })}>Save</button>}
        </div>
        <div className="mt-0.5 text-[11px] text-mute">{inr(v.price_inr)}</div>
      </td>
      <td className="px-4 py-2.5">
        <div className="inline-flex rounded-lg border border-line p-0.5 text-xs" role="group" aria-label={`Status for ${v.model}`}>
          {(["available", "sold"] as const).map((s) => (
            <button key={s} onClick={() => v.status !== s && onUpdate(v.id, { status: s })} aria-pressed={v.status === s}
              className={`rounded-md px-2.5 py-1 font-medium capitalize transition ${v.status === s ? (s === "sold" ? "bg-red-600 text-white" : "bg-emerald-600 text-white") : "text-mute hover:text-ink"}`}>{s}</button>
          ))}
        </div>
      </td>
      <td className="px-4 py-2.5 text-xs text-mute">{timeAgo(v.updated_at)}</td>
    </tr>
  );
}
