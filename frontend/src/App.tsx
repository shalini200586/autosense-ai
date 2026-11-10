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
    <a href={`#/${id}`} className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${view === id ? "bg-gold text-navy" : "text-white/70 hover:text-white"}`}>
      {icon}{label}
    </a>
  );

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-10 border-b-2 border-gold bg-navy text-white shadow-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-full bg-gold" />
            <span className="text-[15px] font-semibold tracking-tight">AutoSense <span className="text-gold">AI</span></span>
            <span className="chip border-gold/50 text-gold">Demo data</span>
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
