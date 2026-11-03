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


def test_propose_then_apply_over_http():
    booking_id = make_booking()

    proposal = client.post(f"/bookings/{booking_id}/disruption", json={"event": "flight_cancelled"})
    assert proposal.status_code == 200
    body = proposal.json()
    assert body["requires_confirmation"] is True
    assert {o["option_id"] for o in body["options"]} == {
        "reschedule",
        "reschedule_extra_night",
        "cancel_transfers",
    }
    # Proposing alone must not change anything.
    assert client.get(f"/bookings/{booking_id}").json()["total"] == 39700

    applied = client.post(
        f"/bookings/{booking_id}/disruption/apply",
        json={"proposal_id": body["proposal_id"], "option_id": "cancel_transfers"},
    )
    assert applied.status_code == 200
    assert applied.json()["new_total"] == 35440
    assert client.get(f"/bookings/{booking_id}").json()["total"] == 35440


def test_applying_twice_returns_the_same_result():
    booking_id = make_booking()
    pid = client.post(f"/bookings/{booking_id}/disruption", json={"event": "heavy_rain"}).json()[
        "proposal_id"
    ]
    body = {"proposal_id": pid, "option_id": "cancel_affected"}

    first = client.post(f"/bookings/{booking_id}/disruption/apply", json=body).json()
    second = client.post(f"/bookings/{booking_id}/disruption/apply", json=body).json()
    assert first["already_applied"] is False
    assert second["already_applied"] is True
    assert second["new_total"] == first["new_total"] == 33760  # charged once, not twice


def test_a_resolved_disruption_cannot_be_answered_differently():
    booking_id = make_booking()
    pid = client.post(
        f"/bookings/{booking_id}/disruption", json={"event": "flight_cancelled"}
    ).json()["proposal_id"]

    client.post(
        f"/bookings/{booking_id}/disruption/apply",
        json={"proposal_id": pid, "option_id": "cancel_transfers"},
    )
    res = client.post(
        f"/bookings/{booking_id}/disruption/apply",
        json={"proposal_id": pid, "option_id": "reschedule"},
    )
    assert res.status_code == 422


def test_error_codes():
    booking_id = make_booking()

    assert client.post(
        "/bookings/SYN-NOPE/disruption", json={"event": "heavy_rain"}
    ).status_code == 404
    assert client.post(
        f"/bookings/{booking_id}/disruption", json={"event": "earthquake"}
    ).status_code == 422

    pid = client.post(
        f"/bookings/{booking_id}/disruption", json={"event": "flight_cancelled"}
    ).json()["proposal_id"]
    assert client.post(
        f"/bookings/{booking_id}/disruption/apply",
        json={"proposal_id": "P-NOPE", "option_id": "reschedule"},
    ).status_code == 404
    assert client.post(
        f"/bookings/{booking_id}/disruption/apply",
        json={"proposal_id": pid, "option_id": "free_money"},
    ).status_code == 422