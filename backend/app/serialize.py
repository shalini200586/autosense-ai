from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import Vehicle


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:  # SQLite returns naive datetimes; stored values are UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def vehicle_to_dict(v: Vehicle) -> dict[str, Any]:
    return {
        "id": v.id,
        "make": v.make,
        "model": v.model,
        "variant": v.variant,
        "year": v.year,
        "fuel": v.fuel,
        "transmission": v.transmission,
        "body_type": v.body_type,
        "mileage_km": v.mileage_km,
        "price_inr": v.price_inr,
        "status": v.status,
        "is_demo": v.is_demo,
        "version": v.version,
        "created_at": iso(v.created_at),
        "updated_at": iso(v.updated_at),
    }


def fmt_inr(n: int) -> str:
    """Indian digit grouping: 1145000 -> 11,45,000."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def lakh(n: int) -> str:
    v = f"{n / 100000:.2f}".rstrip("0").rstrip(".")
    return f"{v} lakh"
