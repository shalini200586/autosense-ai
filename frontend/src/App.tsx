import { useEffect, useState } from "react";
import { Gauge, MessageSquare } from "lucide-react";
import Assistant from "./Assistant";
import Dealer from "./Dealer";

const route = () => (location.hash.startsWith("#/dealer") ? "dealer" : "assistant");

export default function App() {
  const [view, setView] = useState(route());
  useEffect(() => {
    const h = () => setView(route());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);

  const tab = (id: "assistant" | "dealer", label: string, icon: React.ReactNode) => (
    <a href={`#/${id}`} className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${view === id ? "bg-ink text-white" : "text-mute hover:text-ink"}`}>
      {icon}{label}
    </a>
  );

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold tracking-tight">AutoSense AI</span>
            <span className="chip border-line text-mute">Demo data</span>
          </div>
          <nav className="flex gap-1">
            {tab("assistant", "Customer", <MessageSquare size={15} />)}
            {tab("dealer", "Dealer", <Gauge size={15} />)}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-6">
        {view === "assistant" ? <Assistant /> : <Dealer />}
      </main>
      <footer className="border-t border-line py-4 text-center text-xs text-mute">
        Independent portfolio project · fictional listings · not affiliated with any dealership or vendor
      </footer>
    </div>
  );
}
