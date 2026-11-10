"""Deterministic query understanding for English / Hindi / Hinglish.

No LLM here: budget, transmission, body type, fuel, model and intent are
extracted with rules so core searches are reproducible and verifiable.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_NOT_A_CAR_WORD = {"create", "avenue", "value", "price", "about", "what", "with", "under", "lakh", "lakhs", "good",
                   "mileage", "budget", "other", "these", "those", "sedan", "petrol", "diesel", "automatic", "manual",
                   "hatchback", "cheap", "best", "show", "cars", "something", "available", "stock", "which"}

MODEL_ALIASES = {
    "ह्युंडई": "hyundai", "हुंडई": "hyundai", "हुंडे": "hyundai", "टाटा": "tata", "मारुति": "maruti", "मारुती": "maruti",
    "किआ": "kia", "कीआ": "kia", "महिंद्रा": "mahindra", "होंडा": "honda", "टोयोटा": "toyota",
    "क्रेटा": "creta", "सेल्टोस": "seltos", "नेक्सन": "nexon", "ब्रेज़ा": "brezza", "ब्रेजा": "brezza",
    "वेन्यू": "venue", "स्विफ्ट": "swift", "हैरियर": "harrier", "इनोवा": "innova crysta",
    "क्रिस्टा": "innova crysta", "सिटी": "city", "एक्सयूवी700": "xuv700", "एक्सयूवी300": "xuv300",
    "innova": "innova crysta", "crysta": "innova crysta",
}

TRANSMISSION = {
    "Automatic": ["automatic", "auto", "amt", "ऑटोमैटिक", "ऑटोमेटिक", "ऑटो", "स्वचालित"],
    "Manual": ["manual", "मैनुअल", "मेन्युअल", "गियर वाली"],
}
BODY = {
    "SUV": ["suv", "एसयूवी", "एस यू वी"],
    "Sedan": ["sedan", "सेडान"],
    "Hatchback": ["hatchback", "हैचबैक", "हैचबेक"],
    "MPV": ["mpv", "एमपीवी", "7 seater", "seven seater"],
}
FUEL = {
    "Petrol": ["petrol", "पेट्रोल"],
    "Diesel": ["diesel", "डीजल", "डीज़ल"],
    "CNG": ["cng", "सीएनजी"],
    "Electric": ["electric", "इलेक्ट्रिक"],
}
MIN_WORDS = ["above", "over", "at least", "more than", "se zyada", "se jyada", "se upar", "से ज्यादा", "से ज़्यादा", "से ऊपर"]
HINGLISH_MARKERS = {
    "mujhe", "chahiye", "chahie", "ke andar", "andar", "kitna", "kitni", "hai", "hain", "wali", "wala", "kya",
    "dikhao", "batao", "gaadi", "gadi", "tak", "kaisi", "dikha", "mein", "aur", "bhi", "nahi",
    "karwana", "dekhna", "bik", "sasti", "sasta", "kam", "zyada",
}
TEST_DRIVE = ["test drive", "testdrive", "टेस्ट ड्राइव", "test-drive", "drive karna", "drive dekhna"]
COMPARE = ["compare", "comparison", "vs", "versus", "तुलना", "kaun sa behtar", "which is better", "difference"]
PRICE_WORDS = ["price", "cost", "kitne", "kitna", "kimat", "keemat", "कीमत", "क़ीमत", "दाम", "rate", "how much"]
GREETING = ["hello", "hi", "hey", "namaste", "namaskar", "नमस्ते", "नमस्कार"]


@dataclass
class Criteria:
    max_price: int | None = None
    min_price: int | None = None
    transmission: str | None = None
    body_type: str | None = None
    fuel: str | None = None
    models: list[str] = field(default_factory=list)
    makes: list[str] = field(default_factory=list)
    vehicle_ids: list[str] = field(default_factory=list)
    ordinal: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    def has_filters(self) -> bool:
        return any([self.max_price, self.min_price, self.transmission, self.body_type, self.fuel, self.models, self.makes])


@dataclass
class Parsed:
    language: str
    intent: str
    criteria: Criteria


def detect_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    low = text.lower()
    words = set(re.findall(r"[a-z]+", low))
    hits = len([m for m in HINGLISH_MARKERS if (m in words) or (" " in m and m in low)])
    return "hinglish" if hits >= 1 else "en"


def _has(low: str, words: list[str]) -> bool:
    for w in words:
        if re.search(r"[ऀ-ॿ]", w) or " " in w or "-" in w:
            if w in low:
                return True
        elif re.search(rf"\b{re.escape(w)}\b", low):
            return True
    return False


def _first_key(low: str, table: dict[str, list[str]]) -> str | None:
    for key, words in table.items():
        if _has(low, words):
            return key
    return None


_NUMBER_WORDS = {
    1: ["one", "ek", "एक"], 2: ["two", "do", "दो"], 3: ["three", "teen", "तीन"], 4: ["four", "char", "चार"],
    5: ["five", "paanch", "panch", "पांच", "पाँच"], 6: ["six", "chhe", "chhah", "छह", "छः", "छे"],
    7: ["seven", "saat", "सात"], 8: ["eight", "aath", "आठ"], 9: ["nine", "nau", "नौ"], 10: ["ten", "das", "दस"],
    11: ["eleven", "gyarah", "ग्यारह"], 12: ["twelve", "barah", "baarah", "बारह"], 13: ["thirteen", "terah", "तेरह"],
    14: ["fourteen", "chaudah", "चौदह"], 15: ["fifteen", "pandrah", "पंद्रह", "पन्द्रह"],
    16: ["sixteen", "solah", "सोलह"], 17: ["seventeen", "satrah", "सत्रह"], 18: ["eighteen", "atharah", "अठारह"],
    19: ["nineteen", "unnis", "उन्नीस"], 20: ["twenty", "bees", "बीस"],
}
_WORD_TO_NUM = {w: n for n, ws in _NUMBER_WORDS.items() for w in ws}
_UNITS = r"(?:lakh|lakhs|lac|lacs|लाख)"


def _words_to_digits(t: str) -> str:
    """'barah lakh' / 'बारह लाख' / 'twelve lakh' -> '12 lakh' (speech-to-text returns number words)."""
    def sub(m: re.Match) -> str:
        n = _WORD_TO_NUM.get(m.group(1))
        return f"{n} {m.group(2)}" if n else m.group(0)

    return re.sub(rf"(?<![\wऀ-ॿ])([a-zऀ-ॿ]+)\s+({_UNITS})", sub, t)


def parse_budget(text: str) -> tuple[int | None, int | None]:
    t = _words_to_digits(text.translate(_DEV_DIGITS).lower())
    value: int | None = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l\b|लाख)", t)
    if m:
        value = int(round(float(m.group(1)) * 100_000))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:crore|cr\b|करोड़|करोड)", t)
        if m:
            value = int(round(float(m.group(1)) * 10_000_000))
        else:
            m = re.search(r"(\d{1,3}(?:,\d{2,3})+|\d{5,8})", t)
            if m:
                value = int(m.group(1).replace(",", ""))
    if value is None or value <= 0:
        return None, None
    is_min = any(w in t for w in MIN_WORDS)
    return (value, None) if not is_min else (None, value)


def parse(text: str, catalog: list[tuple[str, str]], last_vehicle_ids: list[str] | None = None) -> Parsed:
    """catalog: list of (make, model) pairs from the DB."""
    low = text.lower().translate(_DEV_DIGITS)
    for dev, latin in MODEL_ALIASES.items():
        if dev in low:
            low += f" {latin}"
    # Typo tolerance for makes/models: "hyndai" -> hyundai, "creata" -> creta.
    vocab: dict[str, str] = {}
    for make, model in catalog:
        vocab[make.lower().split()[0]] = make.lower().split()[0]
        for w in model.lower().split():
            vocab[w] = model.lower()
    vocab = {w: full for w, full in vocab.items() if len(w) >= 4}
    for tok in set(re.findall(r"[a-z0-9]{4,}", low)):
        if tok in vocab or tok in _NOT_A_CAR_WORD:
            continue
        near = difflib.get_close_matches(tok, vocab.keys(), n=1, cutoff=0.82)
        if near and tok[0] == near[0][0]:
            low += f" {vocab[near[0]]}"
    lang = detect_language(text)
    c = Criteria()
    c.max_price, c.min_price = parse_budget(text)
    c.transmission = _first_key(low, TRANSMISSION)
    c.body_type = _first_key(low, BODY)
    c.fuel = _first_key(low, FUEL)
    for make, model in catalog:
        ml = model.lower()
        if re.search(rf"(?<![a-z0-9]){re.escape(ml)}(?![a-z0-9])", low) and model not in c.models:
            c.models.append(model)
    for make in {m for m, _ in catalog}:
        first = make.lower().split()[0]
        if re.search(rf"\b{re.escape(first)}\b", low) and make not in c.makes and not c.models:
            c.makes.append(make)
    c.vehicle_ids = [v.upper() for v in re.findall(r"\bas-\d{4}\b", low)]
    ord_map = {"first": 1, "1st": 1, "pehli": 1, "pehla": 1, "पहली": 1, "पहला": 1,
               "second": 2, "2nd": 2, "doosri": 2, "dusri": 2, "दूसरी": 2, "दूसरा": 2,
               "third": 3, "3rd": 3, "teesri": 3, "तीसरी": 3, "तीसरा": 3}
    for w, n in ord_map.items():
        if re.search(rf"(?<![a-zऀ-ॿ]){w}(?![a-zऀ-ॿ])", low):
            c.ordinal = n
            break

    if _has(low, TEST_DRIVE):
        intent = "test_drive"
    elif _has(low, COMPARE) and len(c.models) >= 2:
        intent = "compare"
    elif c.models and (_has(low, PRICE_WORDS) or not (c.max_price or c.transmission or c.body_type or c.fuel)):
        intent = "model_info"
    elif c.has_filters():
        intent = "search"
    elif _has(low, GREETING) and len(low.split()) <= 4:
        intent = "greeting"
    elif _has(low, ["available", "stock", "inventory", "cars", "gaadi", "gadi", "गाड़ी", "गाडी", "कार"]):
        intent = "search"
    else:
        intent = "unknown"
    return Parsed(language=lang, intent=intent, criteria=c)
