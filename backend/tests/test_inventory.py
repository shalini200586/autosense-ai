from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeRedis, make_settings, unreachable_ollama


def test_initial_seed(client):
    data = client.get("/api/vehicles").json()
    assert data["counts"] == {"total": 12, "available": 11, "sold": 1}
    assert len({v["id"] for v in data["vehicles"]}) == 12
    assert all(v["is_demo"] for v in data["vehicles"])
    sold = [v for v in data["vehicles"] if v["status"] == "sold"]
    assert sold
    autosuv = [v for v in data["vehicles"] if v["transmission"] == "Automatic" and v["body_type"] == "SUV"
               and v["price_inr"] < 1_200_000 and v["status"] == "available"]
    assert len(autosuv) >= 3


def test_persistence_across_restart(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, redis_client=FakeRedis(), ollama_transport=unreachable_ollama())) as c:
        assert c.patch("/api/vehicles/AS-1003", json={"price_inr": 777000, "status": "sold"}).status_code == 200
    with TestClient(create_app(settings, redis_client=FakeRedis(), ollama_transport=unreachable_ollama())) as c2:
        v = c2.get("/api/vehicles/AS-1003").json()
        assert v["price_inr"] == 777000 and v["status"] == "sold"
        assert c2.get("/api/vehicles").json()["counts"]["total"] == 12  # not re-seeded


def test_price_change_and_version(client):
    r = client.patch("/api/vehicles/AS-1001", json={"price_inr": 1100000})
    assert r.status_code == 200
    assert r.json()["price_inr"] == 1100000 and r.json()["version"] == 2
    assert client.get("/api/vehicles/AS-1001").json()["price_inr"] == 1100000


def test_invalid_updates_rejected(client):
    for body in ({"price_inr": -5}, {"price_inr": 0}, {"status": "reserved"}, {}, {"price_inr": 10, "bogus": 1}):
        assert client.patch("/api/vehicles/AS-1001", json=body).status_code == 422, body
    assert client.patch("/api/vehicles/NOPE", json={"price_inr": 5}).status_code == 404
    assert client.patch("/api/vehicles/AS-1001", json={"price_inr": 5, "expected_version": 99}).status_code == 409
    assert client.get("/api/vehicles/AS-1001").json()["price_inr"] == 1145000


def test_list_filters(client):
    assert all(v["status"] == "sold" for v in client.get("/api/vehicles?status=sold").json()["vehicles"])
    assert all(v["body_type"] == "Sedan" for v in client.get("/api/vehicles?type=sedan").json()["vehicles"])
    assert [v["model"] for v in client.get("/api/vehicles?q=creta").json()["vehicles"]] == ["Creta"]
    assert client.get("/api/vehicles?status=bogus").status_code == 422


def test_admin_token_enforced_when_configured(tmp_path):
    s = make_settings(tmp_path, admin_token="secret")
    with TestClient(create_app(s, redis_client=FakeRedis(), ollama_transport=unreachable_ollama())) as c:
        assert c.patch("/api/vehicles/AS-1001", json={"price_inr": 1}).status_code == 401
        ok = c.patch("/api/vehicles/AS-1001", json={"price_inr": 1000000}, headers={"X-Admin-Token": "secret"})
        assert ok.status_code == 200


def test_cors_restricted(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
