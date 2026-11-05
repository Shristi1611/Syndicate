import pytest
from fastapi.testclient import TestClient

from app import bookings, seasons
from app.bookings import confirm_quote, create_quote
from app.chat import apply_updates, chat_turn
from app.config import settings
from app.inventory import get_item, get_supplier, list_price
from app.main import app
from app.planner import plan_trip
from app.profile import TravellerProfile
from app.trip import negotiate_plan
from datetime import date

BASE = {
    "destination": "Goa",
    "nights": 4,
    "travellers": 3,
    "budget_total": 120000,
    "stairs_free": True,
    "interests": ["quiet"],
}
PEAK = {**BASE, "start_date": "2026-12-20"}
QUIET = {**BASE, "start_date": "2027-07-10"}

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Fresh empty database and the free mock model for every test."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def hotel_of(plan):
    line = plan["items"][0]
    return line, get_item(line["item_id"])


def test_undated_plans_are_unchanged():
    plan = plan_trip(BASE)
    line, hotel = hotel_of(plan)
    assert plan["stay"] is None
    assert line["unit_price"] == list_price(hotel)
    assert plan["notes"] == []


def test_peak_season_costs_more():
    plan = plan_trip(PEAK)
    line, hotel = hotel_of(plan)
    expected = seasons.adjust(list_price(hotel), seasons.hotel_factor("Goa", date(2026, 12, 20), 4))

    assert line["unit_price"] == expected
    assert expected > list_price(hotel)
    assert plan["list_total"] > plan_trip(BASE)["list_total"]
    assert plan["list_total"] == sum(item["total"] for item in plan["items"])

    assert plan["stay"]["season"] == "peak season"
    assert plan["stay"]["start_date"] == "2026-12-20"
    assert plan["stay"]["end_date"] == "2026-12-24"
    assert plan["stay"]["hotel_change_pct"] > 20
    assert any("peak season" in note.lower() for note in plan["notes"])


def test_quiet_season_costs_less():
    plan = plan_trip(QUIET)
    line, hotel = hotel_of(plan)
    expected = seasons.adjust(list_price(hotel), seasons.hotel_factor("Goa", date(2027, 7, 10), 4))

    assert line["unit_price"] == expected
    assert expected < list_price(hotel)
    assert plan["stay"]["season"] == "quiet season"
    assert any("quiet season" in note.lower() and "below" in note for note in plan["notes"])


def test_tours_and_transfers_stay_flat():
    for profile in (PEAK, QUIET):
        plan = plan_trip(profile)
        for line in plan["items"][1:]:
            assert line["unit_price"] == list_price(get_item(line["item_id"]))


def test_negotiation_respects_the_seasonal_floor():
    trip = negotiate_plan(PEAK)
    line = trip["items"][0]
    hotel = get_item(line["item_id"])
    supplier = get_supplier(hotel["supplier_id"])
    seasonal_floor = round(line["unit_price"] * supplier["floor_ratio"])

    assert seasonal_floor <= line["final_unit_price"] <= line["unit_price"]
    assert line["saved"] > 0
    # In peak season even a good deal can cost more than the year-round list price.
    assert line["final_unit_price"] > list_price(hotel)
    assert trip["stay"]["season"] == "peak season"


def test_a_peak_trip_books_and_a_cheap_price_is_refused():
    trip = negotiate_plan(PEAK)
    booking = confirm_quote(create_quote(trip)["quote_id"])
    assert booking["status"] == "confirmed"
    assert booking["voucher"]["profile"]["start_date"] == "2026-12-20"

    cheat = negotiate_plan(PEAK)
    cheat["items"][0]["final_unit_price"] = 6000  # fine against the year-round floor, not the peak one
    with pytest.raises(ValueError, match="floor"):
        create_quote(cheat)


def test_chat_reads_the_start_date():
    dated = chat_turn("Goa, 2026-12-20, 4 nights, 3 people, Rs 120k", {})
    assert dated["profile"]["start_date"] == "2026-12-20"
    assert dated["complete"] is True
    assert "first night" not in dated["reply"]

    undated = chat_turn("Goa, 4 nights, 3 people, Rs 120k", {})
    assert undated["profile"]["start_date"] is None
    assert undated["complete"] is True
    assert "first night" in undated["reply"]


def test_bad_dates_are_refused():
    with pytest.raises(ValueError):
        TravellerProfile(start_date="2026-13-45")
    with pytest.raises(ValueError):
        plan_trip({**BASE, "start_date": "next friday"})


def test_chat_ignores_a_bad_date():
    profile = apply_updates(TravellerProfile(destination="Goa"), {"start_date": "31-12-2026"})
    assert profile.start_date is None

    good = apply_updates(TravellerProfile(destination="Goa"), {"start_date": "2026-12-20"})
    assert good.start_date == "2026-12-20"


def test_plan_endpoint_rejects_a_bad_date():
    res = client.post("/plan", json={"profile": {**BASE, "start_date": "nope"}})
    assert res.status_code == 422

    ok = client.post("/plan", json={"profile": PEAK})
    assert ok.status_code == 200
    assert ok.json()["stay"]["season"] == "peak season"