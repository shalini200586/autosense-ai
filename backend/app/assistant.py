"""Inventory-grounded assistant.

PostgreSQL is queried directly on every chat turn (never via cache). Cards are
built from DB rows. The LLM, when used, only words a reply from those rows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, nlu
from .config import Settings
from .models import TestDriveRequest, Vehicle
from .schemas import ChatRequest, ChatResponse
from .serialize import fmt_inr, iso, lakh, vehicle_to_dict

MAX_RESULTS = 4


def _name(d: dict[str, Any]) -> str:
    return f"{d['make']} {d['model']} {d['variant']} ({d['year']})"


def _desc(c: nlu.Criteria) -> str:
    parts = []
    if c.transmission:
        parts.append(c.transmission.lower())
    if fuelled := c.fuel:
        parts.append(fuelled.lower())
    parts.append(c.body_type if c.body_type else "car")
    s = " ".join(parts)
    if c.max_price:
        s += f" under ₹{lakh(c.max_price)}"
    if c.min_price:
        s += f" above ₹{lakh(c.min_price)}"
    return s


def _line(d: dict[str, Any]) -> str:
    return f"{_name(d)} – ₹{fmt_inr(d['price_inr'])} (₹{lakh(d['price_inr'])})"


def _query(session: Session, c: nlu.Criteria, *, only_available: bool, ignore_price: bool = False) -> list[Vehicle]:
    q = select(Vehicle)
    if only_available:
        q = q.where(Vehicle.status == "available")
    if c.transmission:
        q = q.where(Vehicle.transmission == c.transmission)
    if c.body_type:
        q = q.where(Vehicle.body_type == c.body_type)
    if c.fuel:
        q = q.where(Vehicle.fuel == c.fuel)
    if c.models:
        q = q.where(Vehicle.model.in_(c.models))
    elif c.makes:
        q = q.where(Vehicle.make.in_(c.makes))
    if not ignore_price:
        if c.max_price:
            q = q.where(Vehicle.price_inr <= c.max_price)
        if c.min_price:
            q = q.where(Vehicle.price_inr >= c.min_price)
    return list(session.scalars(q.order_by(Vehicle.price_inr.asc(), Vehicle.id.asc())))


# ---- rule-based replies -------------------------------------------------------------

def _t(lang: str, en: str, hinglish: str, hi: str) -> str:
    return {"en": en, "hinglish": hinglish, "hi": hi}[lang]


def _reply_search(lang: str, c: nlu.Criteria, vs: list[dict], alts: list[dict]) -> str:
    d = _desc(c)
    if vs:
        lines = "\n".join(f"{i}. {_line(v)}" for i, v in enumerate(vs, 1))
        return _t(
            lang,
            f"I found {len(vs)} available {d} in live inventory:\n{lines}\nPrices are from the dealership database.",
            f"Live inventory mein {len(vs)} available {d} mili hain:\n{lines}\nPrices dealership database se verified hain.",
            f"लाइव इन्वेंटरी में {len(vs)} उपलब्ध गाड़ियाँ मिलीं ({d}):\n{lines}\nकीमतें डीलरशिप डेटाबेस से सत्यापित हैं।",
        )
    if alts:
        lines = "\n".join(f"{i}. {_line(v)}" for i, v in enumerate(alts, 1))
        return _t(
            lang,
            f"No available {d} right now. Closest options above your budget:\n{lines}",
            f"Abhi koi available {d} nahi hai. Budget se thodi upar ye options hain:\n{lines}",
            f"अभी कोई उपलब्ध {d} नहीं है। बजट से थोड़ी ऊपर ये विकल्प हैं:\n{lines}",
        )
    return _t(
        lang,
        f"No available {d} right now. Try a different budget or body type.",
        f"Abhi koi available {d} nahi hai. Budget ya body type badal kar dekhiye.",
        f"अभी कोई उपलब्ध {d} नहीं है। बजट या बॉडी टाइप बदलकर देखें।",
    )


def _reply_model_info(lang: str, vs: list[dict]) -> str:
    if not vs:
        return _t(lang, "I don't have that model in the inventory.",
                  "Ye model inventory mein nahi hai.", "यह मॉडल इन्वेंटरी में नहीं है।")
    rows = []
    for v in vs:
        st = {"available": _t(lang, "available", "available", "उपलब्ध"),
              "sold": _t(lang, "SOLD", "SOLD (bik chuki hai)", "बिक चुकी है")}[v["status"]]
        rows.append(f"- {_line(v)} – {st}")
    return _t(lang, "Here is what the inventory shows:\n", "Inventory mein ye dikh raha hai:\n",
              "इन्वेंटरी में यह दिख रहा है:\n") + "\n".join(rows)


def _reply_compare(lang: str, vs: list[dict]) -> str:
    rows = [f"- {_name(v)}: ₹{fmt_inr(v['price_inr'])}, {v['fuel']}, {v['transmission']}, "
            f"{fmt_inr(v['mileage_km'])} km, {v['status']}" for v in vs]
    head = _t(lang, "Comparison from verified inventory data:\n", "Verified inventory data ke hisaab se comparison:\n",
              "सत्यापित इन्वेंटरी डेटा के अनुसार तुलना:\n")
    return head + "\n".join(rows)


# ---- main entry --------------------------------------------------------------------

async def handle_chat(req: ChatRequest, session: Session, settings: Settings,
                      ollama_transport: httpx.AsyncBaseTransport | None = None) -> ChatResponse:
    catalog = list(session.execute(select(Vehicle.make, Vehicle.model).distinct()).all())
    parsed = nlu.parse(req.message, [(m, mo) for m, mo in catalog], req.last_vehicle_ids)
    c, lang, intent = parsed.criteria, parsed.language, parsed.intent
    checked_at = iso(datetime.now(timezone.utc))

    vehicles: list[dict] = []
    alternatives: list[dict] = []
    td_id: int | None = None
    use_llm = False
    fallback_reply = ""

    if intent == "search":
        rows = _query(session, c, only_available=True)
        vehicles = [vehicle_to_dict(v) for v in rows[:MAX_RESULTS]]
        if not vehicles and c.max_price:
            alt = _query(session, c, only_available=True, ignore_price=True)
            alternatives = [vehicle_to_dict(v) for v in alt[:2]]
        fallback_reply = _reply_search(lang, c, vehicles, alternatives)
        use_llm = True
    elif intent == "model_info":
        rows = _query(session, nlu.Criteria(models=c.models), only_available=False)
        vehicles = [vehicle_to_dict(v) for v in rows]
        fallback_reply = _reply_model_info(lang, vehicles)
        use_llm = bool(vehicles)
    elif intent == "compare":
        rows = _query(session, nlu.Criteria(models=c.models), only_available=False)
        vehicles = [vehicle_to_dict(v) for v in rows]
        fallback_reply = _reply_compare(lang, vehicles)
        use_llm = bool(vehicles)
    elif intent == "test_drive":
        target = _resolve_test_drive_target(session, c, req.last_vehicle_ids)
        if target is None:
            fallback_reply = _t(
                lang,
                "Which car would you like to test drive? Name the model or its ID (for example AS-1003).",
                "Kaun si gaadi ka test drive chahiye? Model ka naam ya ID (jaise AS-1003) batayiye.",
                "आप किस गाड़ी का टेस्ट ड्राइव चाहते हैं? मॉडल का नाम या ID (जैसे AS-1003) बताइए।",
            )
        elif target.status != "available":
            vehicles = [vehicle_to_dict(target)]
            fallback_reply = _t(
                lang,
                f"{_name(vehicles[0])} is already SOLD, so I can't request a test drive for it.",
                f"{_name(vehicles[0])} bik chuki hai (SOLD), isliye iska test drive request nahi ho sakta.",
                f"{_name(vehicles[0])} बिक चुकी है (SOLD), इसलिए टेस्ट ड्राइव अनुरोध नहीं हो सकता।",
            )
        else:
            rec = TestDriveRequest(vehicle_id=target.id, note=req.message[:300])
            session.add(rec)
            session.commit()
            td_id = rec.id
            vehicles = [vehicle_to_dict(target)]
            fallback_reply = _t(
                lang,
                f"Test-drive request #{rec.id} recorded for {_name(vehicles[0])}. This is a request only, not a "
                "confirmed booking; the dealership will follow up.",
                f"{_name(vehicles[0])} ke liye test-drive request #{rec.id} record ho gayi. Ye sirf request hai, "
                "confirmed booking nahi; dealership aapse sampark karegi.",
                f"{_name(vehicles[0])} के लिए टेस्ट-ड्राइव अनुरोध #{rec.id} दर्ज हुआ। यह केवल अनुरोध है, "
                "पुष्टि की गई बुकिंग नहीं; डीलरशिप आपसे संपर्क करेगी।",
            )
    elif intent == "greeting":
        fallback_reply = _t(
            lang,
            "Hello! Tell me your budget, body type and transmission, for example “automatic SUV under 12 lakh”.",
            "Namaste! Apna budget, body type aur transmission batayiye, jaise “12 lakh ke andar automatic SUV”.",
            "नमस्ते! अपना बजट, बॉडी टाइप और ट्रांसमिशन बताइए, जैसे “12 लाख के अंदर ऑटोमैटिक SUV”।",
        )
    else:
        fallback_reply = _t(
            lang,
            "I can search inventory by budget, transmission, body type, fuel or model. Try “automatic SUV under 12 lakh”.",
            "Main budget, transmission, body type, fuel ya model se inventory search kar sakta hoon. Try kijiye: “12 lakh ke andar automatic SUV”.",
            "मैं बजट, ट्रांसमिशन, बॉडी टाइप, ईंधन या मॉडल से इन्वेंटरी खोज सकता हूँ। कोशिश करें: “12 लाख के अंदर ऑटोमैटिक SUV”।",
        )

    reply, source, reason = fallback_reply, "fallback", "Deterministic rule-based answer"
    if use_llm:
        facts = {
            "language": lang,
            "intent": intent,
            "customer_max_budget_inr": c.max_price,
            "vehicles": [_fact(v) for v in vehicles],
            "closest_options_above_budget": [_fact(v) for v in alternatives],
            "result_count": len(vehicles),
        }
        try:
            reply = await llm.explain(settings, facts, req.message, transport=ollama_transport)
            # Append the verified list so the text always carries real data.
            source, reason = "ollama", None
            if vehicles or alternatives:
                reply = reply.rstrip() + "\n" + "\n".join(
                    f"{i}. {_line(v)}" for i, v in enumerate(vehicles or alternatives, 1))
        except llm.OllamaUnavailable as exc:
            reason = f"Rule-based fallback: {exc}"
        except llm.OllamaRejected as exc:
            reason = f"Rule-based fallback: AI wording rejected ({exc})"

    return ChatResponse(
        reply=reply, language=lang, intent=intent, criteria=c.as_dict(), vehicles=vehicles,
        alternatives=alternatives, source=source, fallback_reason=reason,
        checked_at=checked_at, test_drive_request_id=td_id,
    )


def _fact(d: dict) -> dict:
    return {"id": d["id"], "name": _name(d), "fuel": d["fuel"], "transmission": d["transmission"],
            "body_type": d["body_type"], "mileage_km": d["mileage_km"], "price_inr": d["price_inr"],
            "price": f"₹{lakh(d['price_inr'])}", "status": d["status"]}


def _resolve_test_drive_target(session: Session, c: nlu.Criteria, last_ids: list[str]) -> Vehicle | None:
    if c.vehicle_ids:
        return session.get(Vehicle, c.vehicle_ids[0])
    if c.models:
        rows = _query(session, nlu.Criteria(models=c.models), only_available=False)
        avail = [v for v in rows if v.status == "available"]
        return (avail or rows or [None])[0]
    if c.ordinal and 0 < c.ordinal <= len(last_ids):
        return session.get(Vehicle, last_ids[c.ordinal - 1])
    if len(last_ids) == 1:
        return session.get(Vehicle, last_ids[0])
    return None
