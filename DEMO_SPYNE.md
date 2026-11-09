# 45-second demo: live inventory sync

**Setup (before recording):** `docker compose up -d`, Ollama running (optional). Open two windows side by side: Customer `http://localhost:8090/#/assistant` and Dealer `http://localhost:8090/#/dealer`. Confirm "Live" shows in the Dealer header. No prior chat.

| Time | Action | Say |
|---|---|---|
| 0:00–0:08 | Customer window: click **"Mujhe 12 lakh ke andar automatic SUV chahiye"**. Four verified cards appear: Nexon ₹8,95,000, Venue ₹10,25,000, Brezza ₹10,60,000, Creta ₹11,45,000. | "A customer asks in Hinglish. The assistant searches live inventory, and every price on these cards comes straight from the database, not from the model." |
| 0:08–0:14 | Point at the badge under the reply (AI-worded, or "Rule-based fallback" if Ollama is off). | "If the language model is unavailable it says so and falls back to rules. Same verified data." |
| 0:14–0:24 | Dealer window: on **Hyundai Venue** (AS-1006) click **Sold**. The row flashes; the event log shows `status: available → sold`; Redis **Invalidations** goes +1. | "The dealer marks the Venue sold. PostgreSQL commits, Redis is invalidated, and a WebSocket event goes out." |
| 0:24–0:31 | Customer window: amber notice appears under the earlier answer: "Inventory updated… may be outdated." The old answer is **not** rewritten. | "The customer is told the earlier answer may be stale. We never silently rewrite it." |
| 0:31–0:40 | Customer window: send the same question again. Cards now: Nexon, Brezza, Creta, **Seltos**. The Venue is gone. | "Asked again, the app re-queries PostgreSQL and the sold car no longer appears." |
| 0:40–0:45 | Dealer window: point at Redis diagnostics (hits / misses / invalidations are real counters). | "Cache-aside for vehicle details, invalidated on every write. Lists and chat bypass the cache." |

**After:** click **Available** on the Venue to restore the demo. Automated version: `python scripts/demo_check.py`.
