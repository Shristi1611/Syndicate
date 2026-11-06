from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import bookings, market, postbooking
from app.bookings import confirm_quote, create_quote
from app.config import settings
from app.inventory import HOTELS, get_item
from app.main import app
from app.planner import plan_trip
from app.trip import negotiate_plan

START = date(2026, 12, 20)
PEAK = {
    "destination": "Goa",
    "start_date": "2026-12-20",
    "nights": 4,
    "travellers": 3,
    "budget_total": 120000,
    "stairs_free": True,
    "interests": ["quiet"],
}
OPEN = {**PEAK, "stairs_free": False}  # all four Goa hotels are allowed

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Market on, a fresh empty database, and the free mock model."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "market_enabled", True)
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def book(profile):
    trip = negotiate_plan(profile)
    return confirm_quote(create_quote(trip)["quote_id"])["booking_id"], trip


def test_nothing_changes_while_the_market_is_off(monkeypatch):
    monkeypatch.setattr(settings, "market_enabled", False)
    before = plan_trip(PEAK)
    market.set_shock("Goa", "surge")  # stored, but ignored while the market is off
    after = plan_trip(PEAK)
    assert after == before
    assert before["market"] is None


def test_shock_controls_refuse_to_work_while_off(monkeypatch):
    monkeypatch.setattr(settings, "market_enabled", False)
    assert client.post("/market/shock", json={"destination": "Goa", "kind": "surge"}).status_code == 409
    assert client.post("/market/reset").status_code == 409
    assert client.get("/market").json()["enabled"] is False


def test_a_dated_plan_reports_the_market():
    info = plan_trip(PEAK)["market"]
    assert set(info) == {"demand", "hotel_occupancy_pct", "hotel_price_pressure_pct", "sold_out_hotels"}
    assert info["demand"] == 1.0
    assert 0 <= info["hotel_occupancy_pct"] <= 100
    assert info["sold_out_hotels"] >= 0

    undated = {key: value for key, value in PEAK.items() if key != "start_date"}
    assert plan_trip(undated)["market"] is None  # no dates, no market


def test_the_market_is_deterministic():
    first, second = market.snapshot(), market.snapshot()
    for hotel in HOTELS.values():
        assert first.free_rooms(hotel, START, 4) == second.free_rooms(hotel, START, 4)
        assert first.price_pressure(hotel, START, 4) == second.price_pressure(hotel, START, 4)


def test_surge_never_loosens_and_slump_never_tightens():
    normal = market.snapshot()
    market.set_shock("Goa", "surge")
    surge = market.snapshot()
    market.set_shock("Goa", "slump")  # a new shock replaces the old one
    slump = market.snapshot()

    goa = [hotel for hotel in HOTELS.values() if hotel["destination"] == "Goa"]
    assert goa
    for hotel in goa:
        assert surge.free_rooms(hotel, START, 4) <= normal.free_rooms(hotel, START, 4)
        assert normal.free_rooms(hotel, START, 4) <= slump.free_rooms(hotel, START, 4)
        assert surge.price_pressure(hotel, START, 4) >= normal.price_pressure(hotel, START, 4)
        assert normal.price_pressure(hotel, START, 4) >= slump.price_pressure(hotel, START, 4)


def test_a_booking_uses_a_room_and_a_cancellation_returns_it():
    free_before = None
    trip = negotiate_plan(PEAK)
    hotel = get_item(trip["items"][0]["item_id"])
    rooms = trip["items"][0]["quantity"] // PEAK["nights"]
    free_before = market.snapshot().free_rooms(hotel, START, 4)

    booking_id = confirm_quote(create_quote(trip)["quote_id"])["booking_id"]
    assert market.snapshot().free_rooms(hotel, START, 4) == free_before - rooms

    postbooking.cancel_confirm(booking_id, 30)
    assert market.snapshot().free_rooms(hotel, START, 4) == free_before


def test_prices_rise_as_a_hotel_fills():
    pinned = {**PEAK, "hotel_id": "H_GOA_04"}  # eight rooms, so it still has space after one booking
    first = plan_trip(pinned)["items"][0]["unit_price"]
    book(pinned)
    second = plan_trip(pinned)["items"][0]["unit_price"]
    assert second >= first


def test_a_hotel_sells_out_and_the_planner_skips_it():
    pinned = {**OPEN, "hotel_id": "H_GOA_01"}  # six rooms
    booked = 0
    for _ in range(10):
        try:
            trip = negotiate_plan(pinned)
        except ValueError:
            break
        confirm_quote(create_quote(trip)["quote_id"])
        booked += 1
    else:
        pytest.fail("the hotel never sold out")
    assert 0 < booked <= 6

    with pytest.raises(ValueError, match="only 0 room"):
        plan_trip(pinned)

    plan = plan_trip(OPEN)
    assert plan["items"][0]["item_id"] != "H_GOA_01"
    assert any("sold out" in note for note in plan["notes"])


def test_a_quote_goes_stale_when_the_market_moves():
    quote = create_quote(negotiate_plan(PEAK))
    before = [(i["item_id"], i["unit_price"]) for i in plan_trip(PEAK)["items"]]

    market.set_shock("Goa", "surge")
    try:
        after = [(i["item_id"], i["unit_price"]) for i in plan_trip(PEAK)["items"]]
        changed = after != before
    except ValueError:  # everything sold out is also a change
        changed = True
    assert changed

    with pytest.raises(ValueError):
        confirm_quote(quote["quote_id"])


def test_shock_endpoints():
    assert client.get("/market").json() == {"enabled": True, "shocks": []}

    res = client.post("/market/shock", json={"destination": "Goa", "kind": "surge"})
    assert res.status_code == 200
    shocks = res.json()["shocks"]
    assert len(shocks) == 1
    assert shocks[0]["destination"] == "Goa"
    assert shocks[0]["kind"] == "surge"
    assert shocks[0]["level"] == 1.35

    res = client.post("/market/shock", json={"destination": "Goa", "kind": "slump"})
    assert len(res.json()["shocks"]) == 1  # replaced, not stacked
    assert res.json()["shocks"][0]["kind"] == "slump"

    assert client.post("/market/shock", json={"destination": "Atlantis", "kind": "surge"}).status_code == 404
    assert client.post("/market/shock", json={"destination": "Goa", "kind": "earthquake"}).status_code == 422

    assert client.post("/market/reset").json()["shocks"] == []


def test_availability_endpoint(monkeypatch):
    params = {"start_date": "2026-12-20", "nights": 4}
    body = client.get("/availability/H_GOA_01", params=params).json()
    assert body["market_enabled"] is True
    assert body["total_rooms"] == 6
    assert [night["date"] for night in body["nightly"]] == [
        "2026-12-20", "2026-12-21", "2026-12-22", "2026-12-23",
    ]
    assert all(0 <= night["free_rooms"] <= 6 for night in body["nightly"])
    assert body["free_rooms"] == min(night["free_rooms"] for night in body["nightly"])
    assert body["occupancy_pct"] is not None

    monkeypatch.setattr(settings, "market_enabled", False)
    off = client.get("/availability/H_GOA_01", params=params).json()
    assert off["market_enabled"] is False
    assert off["free_rooms"] == 6
    assert off["occupancy_pct"] is None

    assert client.get("/availability/H_NOPE", params=params).status_code == 404
    assert client.get("/availability/H_GOA_01", params={"start_date": "tomorrow"}).status_code == 422