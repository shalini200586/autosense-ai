"""End-to-end check of the sold-car demo against a RUNNING stack (docker compose up).

    backend/.venv/Scripts/python scripts/demo_check.py [base_url]

Default base URL is the nginx front door, http://localhost:8090. Restores the vehicle at the end.
"""
import asyncio
import json
import sys

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"
WS = BASE.replace("http", "ws") + "/ws/inventory"
QUERY = "Mujhe 12 lakh ke andar automatic SUV chahiye."


def chat(c: httpx.Client) -> dict:
    return c.post(f"{BASE}/api/chat", json={"message": QUERY}, timeout=120).json()


async def main() -> None:
    with httpx.Client() as c:
        first = chat(c)
        ids1 = [v["id"] for v in first["vehicles"]]
        print("1. before :", ids1, "| source:", first["source"], "|", first["fallback_reason"])
        print("   reply  :", first["reply"].splitlines()[0])
        target = ids1[1]  # sell the second recommendation
        stats0 = c.get(f"{BASE}/api/diagnostics").json()["cache"]
        c.get(f"{BASE}/api/vehicles/{target}")
        r = c.get(f"{BASE}/api/vehicles/{target}")
        print("2. cache  : second detail read X-Cache =", r.headers["x-cache"])

        async with websockets.connect(WS, origin=BASE) as ws:
            print("3. ws     :", json.loads(await ws.recv())["type"])
            c.patch(f"{BASE}/api/vehicles/{target}", json={"status": "sold"}).raise_for_status()
            ev = json.loads(await asyncio.wait_for(ws.recv(), 5))
            print("4. event  :", ev["type"], ev["vehicle_id"], ev["changes"])

        after = chat(c)
        ids2 = [v["id"] for v in after["vehicles"]]
        print("5. after  :", ids2)
        stats1 = c.get(f"{BASE}/api/diagnostics").json()["cache"]
        print("6. redis  : hits +%d, misses +%d, invalidations +%d" % (
            stats1["hits"] - stats0["hits"], stats1["misses"] - stats0["misses"],
            stats1["invalidations"] - stats0["invalidations"]))
        post = c.get(f"{BASE}/api/vehicles/{target}")
        print("7. detail : status =", post.json()["status"], "| X-Cache =", post.headers["x-cache"])

        c.patch(f"{BASE}/api/vehicles/{target}", json={"status": "available"})  # restore
        assert target in ids1 and target not in ids2, "sold car must disappear from recommendations"
        assert ev["vehicle_id"] == target and ev["changes"]["status"]["to"] == "sold"
        assert post.json()["status"] == "sold" and post.headers["x-cache"] == "MISS"
        print("\nPASS: sold vehicle", target, "was excluded from the next recommendation.")


asyncio.run(main())
