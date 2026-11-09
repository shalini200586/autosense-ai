def test_cache_hit_miss_invalidation(client, redis_fake):
    r1 = client.get("/api/vehicles/AS-1002")
    r2 = client.get("/api/vehicles/AS-1002")
    assert r1.headers["x-cache"] == "MISS" and r2.headers["x-cache"] == "HIT"
    assert "vehicle:AS-1002" in redis_fake.store
    client.patch("/api/vehicles/AS-1002", json={"price_inr": 1150000})
    assert "vehicle:AS-1002" not in redis_fake.store
    r3 = client.get("/api/vehicles/AS-1002")
    assert r3.headers["x-cache"] == "MISS" and r3.json()["price_inr"] == 1150000
    stats = client.get("/api/diagnostics").json()["cache"]
    assert (stats["hits"], stats["misses"], stats["invalidations"]) == (1, 2, 1)


def test_lists_and_chat_are_not_cached(client, redis_fake):
    client.get("/api/vehicles")
    client.post("/api/chat", json={"message": "automatic SUV under 12 lakh"})
    assert redis_fake.store == {}


def test_redis_failure_falls_back_to_postgres(client, redis_fake):
    redis_fake.down = True
    r = client.get("/api/vehicles/AS-1001")
    assert r.status_code == 200 and r.headers["x-cache"] == "BYPASS"
    assert client.patch("/api/vehicles/AS-1001", json={"price_inr": 1111000}).status_code == 200
    assert client.get("/api/vehicles/AS-1001").json()["price_inr"] == 1111000
    assert client.post("/api/chat", json={"message": "automatic SUV 12 lakh"}).status_code == 200
    health = client.get("/api/health").json()
    assert health["redis"] is False and health["database"] is True
    redis_fake.down = False
    assert client.get("/api/health").json()["redis"] is True


def test_websocket_inventory_change(client):
    with client.websocket_connect("/ws/inventory") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.patch("/api/vehicles/AS-1006", json={"status": "sold"})
        ev = ws.receive_json()
        assert ev["type"] == "inventory_changed" and ev["vehicle_id"] == "AS-1006"
        assert ev["changes"]["status"] == {"from": "available", "to": "sold"}
        assert client.get("/api/diagnostics").json()["websocket_clients"] == 1


def test_noop_update_does_not_broadcast_or_invalidate(client):
    client.get("/api/vehicles/AS-1001")
    client.patch("/api/vehicles/AS-1001", json={"price_inr": 1145000})  # same value
    assert client.get("/api/diagnostics").json()["cache"]["invalidations"] == 0


def test_websocket_rejects_foreign_origin(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/inventory", headers={"origin": "http://evil.example"}):
            pass
