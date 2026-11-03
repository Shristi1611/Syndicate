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
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def make_booking() -> str:
    trip = client.post("/trip", json={"profile": PROFILE}).json()
    quote = client.post("/book/quote", json={"trip": trip}).json()
    return client.post("/book/confirm", json={"quote_id": quote["quote_id"]}).json()["booking_id"]


def test_preview_then_confirm_over_http():
    booking_id = make_booking()

    preview = client.post(f"/bookings/{booking_id}/cancel/preview", json={"days_before_trip": 3})
    assert preview.status_code == 200
    assert preview.json()["refund"] == 19850
    assert client.get(f"/bookings/{booking_id}").json()["status"] == "confirmed"

    done = client.post(f"/bookings/{booking_id}/cancel/confirm", json={"days_before_trip": 3})
    assert done.status_code == 200
    assert done.json()["status"] == "cancelled"
    assert client.get(f"/bookings/{booking_id}").json()["status"] == "cancelled"


def test_confirming_twice_returns_the_same_refund():
    booking_id = make_booking()
    body = {"days_before_trip": 10}
    first = client.post(f"/bookings/{booking_id}/cancel/confirm", json=body).json()
    second = client.post(f"/bookings/{booking_id}/cancel/confirm", json=body).json()
    assert second["already_cancelled"] is True
    assert second["refund"] == first["refund"] == 39700


def test_unknown_booking_and_bad_days():
    assert client.post(
        "/bookings/SYN-NOPE/cancel/preview", json={"days_before_trip": 5}
    ).status_code == 404

    booking_id = make_booking()
    res = client.post(f"/bookings/{booking_id}/cancel/preview", json={"days_before_trip": -1})
    assert res.status_code == 422  # rejected before it reaches the booking logic