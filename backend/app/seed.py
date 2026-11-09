"""Synthetic demo inventory. All listings are fictional demo data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Vehicle

# id, make, model, variant, year, fuel, transmission, body, km, price, status
ROWS = [
    ("AS-1001", "Hyundai", "Creta", "1.5 SX AT", 2019, "Petrol", "Automatic", "SUV", 54000, 1145000, "available"),
    ("AS-1002", "Kia", "Seltos", "HTK+ IVT", 2020, "Petrol", "Automatic", "SUV", 41000, 1185000, "available"),
    ("AS-1003", "Tata", "Nexon", "XZ+ AMT", 2020, "Petrol", "Automatic", "SUV", 38500, 895000, "available"),
    ("AS-1004", "Maruti Suzuki", "Brezza", "ZXi+ AT", 2021, "Petrol", "Automatic", "SUV", 29000, 1060000, "available"),
    ("AS-1005", "Mahindra", "XUV300", "W8 AMT", 2020, "Diesel", "Automatic", "SUV", 47000, 975000, "sold"),
    ("AS-1006", "Hyundai", "Venue", "SX DCT", 2021, "Petrol", "Automatic", "SUV", 22000, 1025000, "available"),
    ("AS-1007", "Mahindra", "XUV700", "AX7 AT", 2022, "Diesel", "Automatic", "SUV", 31000, 1950000, "available"),
    ("AS-1008", "Maruti Suzuki", "Swift", "VXi", 2020, "Petrol", "Manual", "Hatchback", 35000, 540000, "available"),
    ("AS-1009", "Honda", "City", "ZX CVT", 2019, "Petrol", "Automatic", "Sedan", 52000, 920000, "available"),
    ("AS-1010", "Toyota", "Innova Crysta", "2.4 GX MT", 2018, "Diesel", "Manual", "MPV", 98000, 1425000, "available"),
    ("AS-1011", "Tata", "Harrier", "XZ", 2020, "Diesel", "Manual", "SUV", 61000, 1340000, "available"),
    ("AS-1012", "Hyundai", "i20", "Asta DCT", 2021, "Petrol", "Automatic", "Hatchback", 27000, 875000, "available"),
]


def seed_if_empty(session: Session) -> bool:
    """Seed only when the vehicles table is empty, so edits survive restarts."""
    if session.scalar(select(func.count()).select_from(Vehicle)):
        return False
    now = datetime.now(timezone.utc)
    for i, (vid, make, model, variant, year, fuel, trans, body, km, price, status) in enumerate(ROWS):
        ts = now - timedelta(hours=i * 3 + 1)
        session.add(Vehicle(
            id=vid, make=make, model=model, variant=variant, year=year, fuel=fuel,
            transmission=trans, body_type=body, mileage_km=km, price_inr=price,
            status=status, is_demo=True, version=1, created_at=ts, updated_at=ts,
        ))
    session.commit()
    return True
