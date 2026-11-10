import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, Mic, Send, Square, Volume2, WifiOff } from "lucide-react";
import { api, ApiError, inr, lakh, type ChatResponse, type Health, type Vehicle } from "./api";
import { useInventorySocket } from "./useInventorySocket";
import { MAX_SECONDS, WavRecorder } from "./wav";

type Msg =
  | { role: "user"; text: string; viaVoice?: boolean }
  | { role: "assistant"; data: ChatResponse; outdatedBy?: string[] }
  | { role: "error"; text: string };

const SUGGESTIONS = [
  "Mujhe 12 lakh ke andar automatic SUV chahiye",
  "Automatic SUV under 12 lakh",
  "Creta ka price kya hai?",
  "मुझे 10 लाख तक की ऑटोमैटिक SUV चाहिए",
];

export default function Assistant() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [rec, setRec] = useState<"idle" | "recording" | "transcribing">("idle");
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState<number | null>(null);
  const recorder = useRef<WavRecorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const lastIds = useRef<string[]>([]);

  const checkHealth = useCallback(() => {
    api.health().then((h) => { setHealth(h); setOffline(false); }).catch(() => setOffline(true));
  }, []);
  useEffect(() => { checkHealth(); const t = setInterval(checkHealth, 10000); return () => clearInterval(t); }, [checkHealth]);
  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);

  // Inventory changed: never rewrite old answers; just flag them as possibly outdated.
  const socket = useInventorySocket((e) => {
    const label = `${e.label ?? e.vehicle_id}: ${Object.entries(e.changes ?? {}).map(([k, c]) => `${k} ${c.from} → ${c.to}`).join(", ")}`;
    setMsgs((p) => p.map((m) => (m.role === "assistant" && (m.data.vehicles.length || m.data.alternatives.length) && m.data.checked_at < e.at
      ? { ...m, outdatedBy: [...(m.outdatedBy ?? []), label] } : m)));
  }, checkHealth);

  const speak = useCallback(async (i: number, text: string, lang: string) => {
    setVoiceNote(null);
    setSpeaking(i);
    try {
      const blob = await api.synthesize(text.replace(/\n+/g, ". "), lang);
      audioRef.current?.pause();
      const a = new Audio(URL.createObjectURL(blob));
      audioRef.current = a;
      a.onended = () => setSpeaking(null);
      await a.play();
    } catch (e) {
      setSpeaking(null);
      setVoiceNote(e instanceof ApiError && e.code === "voice_setup_required" ? "Voice setup required" : `Speech playback unavailable: ${(e as Error).message}`);
    }
  }, []);

  const send = useCallback(async (text: string, viaVoice = false) => {
    const t = text.trim();
    if (!t || busy) return;
    setInput("");
    setMsgs((p) => [...p, { role: "user", text: t, viaVoice }]);
    setBusy(true);
    try {
      const data = await api.chat(t, lastIds.current);
      if (data.vehicles.length) lastIds.current = data.vehicles.map((v) => v.id);
      setMsgs((p) => {
        const next = [...p, { role: "assistant", data } as Msg];
        if (viaVoice && health?.voice_configured) speak(next.length - 1, data.reply, data.language);
        return next;
      });
      setOffline(false);
    } catch (e) {
      if (e instanceof ApiError && e.code === "offline") setOffline(true);
      setMsgs((p) => [...p, { role: "error", text: (e as Error).message }]);
    } finally { setBusy(false); }
  }, [busy, health, speak]);

  const sendRef = useRef(send);
  sendRef.current = send;

  const stopRecording = async () => {
    const r = recorder.current;
    if (!r) return;
    recorder.current = null; // makes auto-stop and manual stop idempotent
    setRec("transcribing");
    try {
      const res = await api.transcribe(await r.stop());
      if (!res.transcript.trim()) setVoiceNote("I couldn't hear anything. Please try again.");
      else await sendRef.current(res.transcript, true);
    } catch (e) {
      setVoiceNote(e instanceof ApiError && e.code === "voice_setup_required" ? "Voice setup required" : `Speech recognition failed: ${(e as Error).message}`);
    } finally { setRec("idle"); }
  };

  const toggleMic = async () => {
    setVoiceNote(null);
    if (recorder.current) return stopRecording();
    try {
      const r = new WavRecorder();
      await r.start(() => void stopRecording());
      recorder.current = r;
      setRec("recording");
    } catch { setVoiceNote("Microphone access was blocked. Allow it in the browser to use voice."); }
  };

  const voiceReady = !!health?.voice_configured && !offline;

  return (
    <div className="mx-auto flex h-[calc(100vh-11rem)] min-h-[480px] max-w-3xl flex-col">
      {offline && (
        <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <WifiOff size={15} /> Can’t reach the assistant right now. Check that the backend is running.
        </div>
      )}
      <div className="flex-1 space-y-5 overflow-y-auto pb-4 pr-1" aria-live="polite">
        {msgs.length === 0 && (
          <div className="animate-rise pt-10 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">Find your next car</h1>
            <p className="mx-auto mt-2 max-w-md text-sm text-mute">Ask in English, Hindi or Hinglish. Every price and availability you see comes from the live dealership inventory.</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => <button key={s} className="btn" onClick={() => send(s)}>{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m, i) => m.role === "user" ? (
          <div key={i} className="flex animate-rise justify-end">
            <div className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm text-white">
              {m.viaVoice && <Mic size={12} className="mr-1.5 inline opacity-70" />}{m.text}
            </div>
          </div>
        ) : m.role === "error" ? (
          <div key={i} role="alert" className="flex animate-rise items-center gap-2 text-sm text-red-700"><AlertTriangle size={15} />{m.text}</div>
        ) : (
          <div key={i} className="animate-rise space-y-3">
            <div className="max-w-[88%] whitespace-pre-line rounded-2xl rounded-bl-md border border-line bg-white px-4 py-3 text-sm leading-relaxed">{m.data.reply}</div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-mute">
              {m.data.source === "ollama"
                ? <span className="chip border-line">AI-worded · prices verified from inventory</span>
                : <span className="chip border-amber-300 bg-amber-50 text-amber-800" title={m.data.fallback_reason ?? ""}>Rule-based fallback{m.data.fallback_reason ? ` · ${m.data.fallback_reason.replace("Rule-based fallback: ", "")}` : ""}</span>}
              <span>checked {new Date(m.data.checked_at).toLocaleTimeString("en-IN")}</span>
              {voiceReady && <button className="btn px-2 py-0.5 text-xs" disabled={speaking === i} onClick={() => speak(i, m.data.reply, m.data.language)}>
                {speaking === i ? <Loader2 size={12} className="animate-spin" /> : <Volume2 size={12} />} Listen</button>}
            </div>
            {m.outdatedBy && (
              <div role="status" className="max-w-[88%] rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <b>Inventory updated</b> since this answer ({m.outdatedBy.join("; ")}). These recommendations may be outdated. Ask again to refresh.
              </div>
            )}
            {(m.data.vehicles.length > 0 || m.data.alternatives.length > 0) && (
              <div className="grid gap-3 sm:grid-cols-2">
                {m.data.alternatives.length > 0 && m.data.vehicles.length === 0 && <p className="col-span-full text-xs text-mute">Above your budget:</p>}
                {(m.data.vehicles.length ? m.data.vehicles : m.data.alternatives).map((v) => <Card key={v.id} v={v} />)}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-sm text-mute"><Loader2 size={15} className="animate-spin" /> Checking live inventory…</div>}
        <div ref={bottom} />
      </div>

      {voiceNote && <p role="status" className="mb-2 text-xs text-amber-800">{voiceNote}</p>}
      <form className="flex items-center gap-2 border-t border-line pt-3" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <button type="button" onClick={toggleMic} disabled={!voiceReady || rec === "transcribing" || busy}
          title={voiceReady ? (rec === "recording" ? "Stop and send" : `Speak (up to ${MAX_SECONDS}s)`) : "Voice setup required"}
          aria-label={rec === "recording" ? "Stop recording" : "Start voice input"}
          className={`btn h-10 w-10 shrink-0 rounded-full p-0 ${rec === "recording" ? "border-red-500 bg-red-500 text-white hover:bg-red-600" : ""}`}>
          {rec === "transcribing" ? <Loader2 size={16} className="animate-spin" /> : rec === "recording" ? <Square size={14} /> : <Mic size={16} />}
        </button>
        <input className="input h-10" value={input} onChange={(e) => setInput(e.target.value)} disabled={rec !== "idle"}
          placeholder={rec === "recording" ? "Listening… tap the square to send" : rec === "transcribing" ? "Transcribing…" : "Ask about budget, body type, model…"} aria-label="Message" maxLength={600} />
        <button className="btn btn-primary h-10 shrink-0" disabled={busy || !input.trim()} aria-label="Send"><Send size={15} /></button>
      </form>
      <div className="mt-2 flex justify-between text-[11px] text-mute">
        <span>{health && !health.voice_configured ? "Voice setup required · text chat is fully available" : "Voice: Gnani Prisma (speech-to-text) · Timbre (text-to-speech)"}</span>
        <span>{socket === "open" ? "Live inventory updates on" : "Reconnecting to live updates…"}</span>
      </div>
    </div>
  );
}

function Card({ v }: { v: Vehicle }) {
  const sold = v.status === "sold";
  return (
    <article className="rounded-xl border border-line bg-white p-4 transition hover:shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{v.make} {v.model}</h3>
          <p className="text-xs text-mute">{v.variant} · {v.year}</p>
        </div>
        <span className={`chip ${sold ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{sold ? "Sold" : "Available"}</span>
      </div>
      <div className="mt-3 text-xl font-semibold tabular-nums">{inr(v.price_inr)}</div>
      <div className="text-xs text-mute">{lakh(v.price_inr)}</div>
      <p className="mt-3 text-xs text-mute">{v.body_type} · {v.fuel} · {v.transmission} · {v.mileage_km.toLocaleString("en-IN")} km</p>
      <p className="mt-2 font-mono text-[10px] text-neutral-400">{v.id} · demo listing</p>
    </article>
  );
}
