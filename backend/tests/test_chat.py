import json
import re

import httpx
from fastapi.testclient import TestClient

from app import llm, nlu
from app.config import Settings
from app.main import create_app
from conftest import FakeRedis, make_settings

QUERIES = [
    "Mujhe 12 lakh ke andar automatic SUV chahiye.",
    "automatic SUV under 12 lakh",
    "मुझे 12 लाख के अंदर ऑटोमैटिक एसयूवी चाहिए",
]


def chat(client, msg, last=None):
    r = client.post("/api/chat", json={"message": msg, "last_vehicle_ids": last or []})
    assert r.status_code == 200, r.text
    return r.json()


def test_core_demo_query_all_languages(client):
    for q in QUERIES:
        d = chat(client, q)
        ids = [v["id"] for v in d["vehicles"]]
        assert d["intent"] == "search"
        assert ids == ["AS-1003", "AS-1006", "AS-1004", "AS-1001"], (q, ids)
        for v in d["vehicles"]:
            assert v["transmission"] == "Automatic" and v["body_type"] == "SUV"
            assert v["price_inr"] <= 1_200_000 and v["status"] == "available"
        assert d["source"] == "fallback" and "AI service unavailable" in d["fallback_reason"]


def test_language_detection():
    assert nlu.detect_language("Mujhe 12 lakh ke andar automatic SUV chahiye") == "hinglish"
    assert nlu.detect_language("मुझे एसयूवी चाहिए") == "hi"
    assert nlu.detect_language("automatic SUV under 12 lakh") == "en"


def test_budget_parsing():
    assert nlu.parse_budget("under 12 lakh") == (1_200_000, None)
    assert nlu.parse_budget("12 लाख के अंदर") == (1_200_000, None)
    assert nlu.parse_budget("budget 9.5 lac") == (950_000, None)
    assert nlu.parse_budget("under ₹10,50,000") == (1_050_000, None)
    assert nlu.parse_budget("above 15 lakh") == (None, 1_500_000)
    assert nlu.parse_budget("show me cars") == (None, None)
    # speech-to-text returns number words
    assert nlu.parse_budget("मुझे बारह लाख के अंदर ऑटोमैटिक एसयूवी चाहिए।") == (1_200_000, None)
    assert nlu.parse_budget("mujhe barah lakh ke andar") == (1_200_000, None)
    assert nlu.parse_budget("automatic SUV under ten lakh") == (1_000_000, None)
    assert nlu.parse_budget("दस लाख तक") == (1_000_000, None)


def test_spoken_number_word_budget_actually_filters(client):
    d = chat(client, "मुझे दस लाख के अंदर ऑटोमैटिक एसयूवी चाहिए।")
    assert d["criteria"]["max_price"] == 1_000_000
    assert [v["id"] for v in d["vehicles"]] == ["AS-1003"]  # only Nexon is <= ₹10 lakh


def test_sold_vehicle_excluded_after_update(client):
    before = [v["id"] for v in chat(client, QUERIES[0])["vehicles"]]
    assert "AS-1006" in before
    client.patch("/api/vehicles/AS-1006", json={"status": "sold"})
    after = [v["id"] for v in chat(client, QUERIES[0])["vehicles"]]
    assert "AS-1006" not in after and after == ["AS-1003", "AS-1004", "AS-1001", "AS-1002"]


def test_price_change_reflected_in_chat(client):
    client.patch("/api/vehicles/AS-1001", json={"price_inr": 1250000})  # now over budget
    ids = [v["id"] for v in chat(client, QUERIES[0])["vehicles"]]
    assert "AS-1001" not in ids


def test_previously_sold_model_reported_as_sold(client):
    d = chat(client, "XUV300 price?")
    assert d["intent"] == "model_info" and d["vehicles"][0]["status"] == "sold"
    assert "SOLD" in d["reply"]


def test_no_match_shows_closest_labelled(client):
    d = chat(client, "automatic SUV under 5 lakh")
    assert d["vehicles"] == [] and d["alternatives"]
    assert all(a["price_inr"] > 500_000 for a in d["alternatives"])


def test_no_fabricated_prices_or_ids(client):
    inv = {v["id"]: v for v in client.get("/api/vehicles").json()["vehicles"]}
    valid_prices = {str(v["price_inr"]) for v in inv.values()}
    for q in QUERIES + ["compare Creta vs Seltos", "Nexon kitne ka hai", "sedan automatic", "diesel SUV"]:
        d = chat(client, q)
        for v in d["vehicles"] + d["alternatives"]:
            assert v == inv[v["id"]]  # card is byte-identical to the DB record
        for price in re.findall(r"₹(\d[\d,]{4,})", d["reply"]):
            assert price.replace(",", "") in valid_prices


def test_compare(client):
    d = chat(client, "compare Creta vs Seltos")
    assert d["intent"] == "compare" and {v["model"] for v in d["vehicles"]} == {"Creta", "Seltos"}


def test_test_drive_is_request_not_booking(client):
    d = chat(client, "I want a test drive of AS-1003")
    assert d["test_drive_request_id"] and "not a" in d["reply"].lower()
    assert "confirmed booking" in d["reply"]
    sold = chat(client, "test drive AS-1005")
    assert sold["test_drive_request_id"] is None and "SOLD" in sold["reply"]
    ambiguous = chat(client, "test drive karna hai")
    assert ambiguous["test_drive_request_id"] is None


def test_chat_input_validation(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 601}).status_code == 422


def test_greeting_and_unknown(client):
    assert chat(client, "namaste")["intent"] == "greeting"
    assert chat(client, "asdf qwerty")["vehicles"] == []


# ---- Groq (OpenAI-compatible) AI-wording behaviour ----------------------------------

def _llm(content: str) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda req: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}))


def _app(tmp_path, transport):
    return TestClient(create_app(make_settings(tmp_path), redis_client=FakeRedis(), llm_transport=transport))


def test_llm_good_answer_used_and_cards_still_from_db(tmp_path):
    with _app(tmp_path, _llm("Here are some verified automatic SUVs within your budget.")) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "llm" and d["fallback_reason"] is None
        assert [v["id"] for v in d["vehicles"]][0] == "AS-1003"


def test_llm_invented_price_rejected(tmp_path):
    with _app(tmp_path, _llm("Great deal: a Creta for just ₹7,50,000!")) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback" and "rejected" in d["fallback_reason"]
        assert "7,50,000" not in d["reply"]


def test_llm_booking_claim_rejected(tmp_path):
    with _app(tmp_path, _llm("Your test drive is confirmed!")) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback"


def test_llm_disabled_flag(tmp_path):
    s = make_settings(tmp_path, llm_enabled=False)
    with TestClient(create_app(s, redis_client=FakeRedis())) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback" and "disabled" in d["fallback_reason"]


def test_llm_request_format(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        import json as _json
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = _json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Here are verified options."}}]})

    with _app(tmp_path, httpx.MockTransport(handler)) as c:
        assert chat(c, QUERIES[0])["source"] == "llm"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer test-groq-key"
    assert seen["body"]["model"] == "llama-3.3-70b-versatile" and seen["body"]["messages"][0]["role"] == "system"
    facts = seen["body"]["messages"][1]["content"]
    assert "AS-1003" in facts and "AS-1005" not in facts  # only verified, available vehicles are shared


def test_llm_not_configured_without_key(tmp_path):
    s = make_settings(tmp_path, groq_api_key="")
    with TestClient(create_app(s, redis_client=FakeRedis())) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback" and "GROQ_API_KEY" in d["fallback_reason"]
        assert [v["id"] for v in d["vehicles"]][0] == "AS-1003"
        assert c.get("/api/health").json()["llm_enabled"] is False


def test_llm_rate_limited_falls_back(tmp_path):
    with _app(tmp_path, httpx.MockTransport(lambda req: httpx.Response(429, json={"error": {"message": "slow down"}}))) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback" and "rate-limited" in d["fallback_reason"]


def test_llm_server_error_falls_back(tmp_path):
    with _app(tmp_path, httpx.MockTransport(lambda req: httpx.Response(503, text="down"))) as c:
        d = chat(c, QUERIES[0])
        assert d["source"] == "fallback" and "HTTP 503" in d["fallback_reason"]


def test_llm_malformed_response_falls_back(tmp_path):
    with _app(tmp_path, httpx.MockTransport(lambda req: httpx.Response(200, json={"unexpected": 1}))) as c:
        assert chat(c, QUERIES[0])["source"] == "fallback"


def test_llm_api_key_never_leaks(tmp_path):
    with _app(tmp_path, _llm("ok")) as c:
        for path in ("/api/health", "/api/diagnostics"):
            assert "test-groq-key" not in c.get(path).text


def test_llm_validate_unit():
    facts = {"vehicles": [{"price_inr": 895000, "price": "₹8.95 lakh", "name": "Tata Nexon (2020)"}]}
    assert llm.validate("Nexon at ₹8,95,000 or 8.95 lakh, 2020 model", facts, "12 lakh")
    for bad in ("only ₹8,50,000", "booking confirmed"):
        try:
            llm.validate(bad, facts, "")
            raise AssertionError("should reject")
        except llm.LLMRejected:
            pass
