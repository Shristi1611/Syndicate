import pytest
from fastapi.testclient import TestClient

from app import bookings
from app.config import settings
from app.main import app

PROFILE = {
    "destination": "Goa",
    "nights": 4,
    "travellers": 3,
    "budget_total": 60000,
    "stairs_free": True,
    "interests": ["quiet"],
}

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Every test gets a fresh empty database and the free mock model."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def negotiated_trip():
    res = client.post("/trip", json={"profile": PROFILE})
    assert res.status_code == 200
    return res.json()


def test_quote_and_confirm_flow():
    trip = negotiated_trip()
    assert trip["final_total"] == 39700

    quote = client.post("/book/quote", json={"trip": trip}).json()
    assert quote["total"] == 39700
    assert quote["saved"] == 10200
    assert quote["requires_confirmation"] is True

    first = client.post("/book/confirm", json={"quote_id": quote["quote_id"]}).json()
    assert first["status"] == "confirmed"
    assert first["booking_id"].startswith("SYN-")

    # Confirming the same quote again must return the same booking, never a second one.
    again = client.post("/book/confirm", json={"quote_id": quote["quote_id"]}).json()
    assert again["booking_id"] == first["booking_id"]

    voucher = client.get(f"/bookings/{first['booking_id']}").json()
    assert len(voucher["voucher"]["items"]) == 5


def test_tampered_price_is_rejected():
    trip = negotiated_trip()
    trip["items"][0]["final_unit_price"] = 100  # far below the hidden floor
    res = client.post("/book/quote", json={"trip": trip})
    assert res.status_code == 422
    assert "floor" in res.json()["detail"]


def test_unknown_quote_is_404():
    res = client.post("/book/confirm", json={"quote_id": "Q-FAKE"})
    assert res.status_code == 404


def test_incomplete_profile_is_422():
    res = client.post("/trip/stream", json={"profile": {"destination": "Goa", "nights": 4}})
    assert res.status_code == 422
    assert "travellers" in res.json()["detail"]


def test_rooms_sell_out():
    trip = negotiated_trip()
    for _ in range(6):  # Palm Cove Resort has 6 rooms, this trip needs 1
        quote = client.post("/book/quote", json={"trip": trip}).json()
        res = client.post("/book/confirm", json={"quote_id": quote["quote_id"]})
        assert res.status_code == 200

    res = client.post("/book/quote", json={"trip": trip})
    assert res.status_code == 422
    assert "room" in res.json()["detail"]


def test_catalogue_does_not_leak_floor_prices():
    text = client.get("/items").text.lower()
    assert "floor" not in text