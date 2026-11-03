import pytest

from app import bookings, postbooking
from app.bookings import confirm_quote, create_quote
from app.config import settings
from app.disruptions import propose
from app.trip import negotiate_plan

PROFILE = {
    "destination": "Goa",
    "nights": 4,
    "travellers": 3,
    "budget_total": 60000,
    "stairs_free": True,
    "interests": ["quiet"],
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Fresh empty database and the free mock model for every test."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def book():
    trip = negotiate_plan(PROFILE)
    booking_id = confirm_quote(create_quote(trip)["quote_id"])["booking_id"]
    return booking_id, trip


def total_of(trip, category):
    return sum(line["final_total"] for line in trip["items"] if line["category"] == category)


def by_id(proposal):
    return {option["option_id"]: option for option in proposal["options"]}


def test_flight_cancelled_options():
    booking_id, trip = book()
    proposal = propose(booking_id, "flight_cancelled")
    options = by_id(proposal)

    assert set(options) == {"reschedule", "reschedule_extra_night", "cancel_transfers"}
    assert options["reschedule"]["cost_delta"] == 0
    assert 0 < options["reschedule_extra_night"]["cost_delta"] <= 7000  # one room, at most list price
    assert options["cancel_transfers"]["cost_delta"] == -total_of(trip, "transfer")
    assert proposal["requires_confirmation"] is True


def test_heavy_rain_affects_only_outdoor_items():
    booking_id, trip = book()
    proposal = propose(booking_id, "heavy_rain")
    options = by_id(proposal)

    assert proposal["affected"] == ["Sunset Beach Dinner"]
    dinner = next(line for line in trip["items"] if line["name"] == "Sunset Beach Dinner")
    assert options["keep_all"]["cost_delta"] == 0
    assert options["cancel_affected"]["cost_delta"] == -dinner["final_total"]


def test_hotel_overbooked_offers_a_move_or_a_refund():
    booking_id, trip = book()
    options = by_id(propose(booking_id, "hotel_overbooked"))
    hotel_total = total_of(trip, "hotel")

    assert options["cancel_hotel"]["cost_delta"] == -hotel_total
    move = options["move:H_GOA_04"]  # the only other stairs-free hotel in Goa
    assert move["cost_delta"] == move["new_unit_price"] * 4 - hotel_total


def test_proposing_changes_nothing():
    booking_id, _ = book()
    for event in ("hotel_overbooked", "heavy_rain", "flight_cancelled"):
        propose(booking_id, event)
    booking = bookings.get_booking(booking_id)
    assert booking["status"] == "confirmed"
    assert booking["total"] == 39700


def test_bad_requests():
    booking_id, _ = book()
    with pytest.raises(ValueError):
        propose(booking_id, "earthquake")
    with pytest.raises(LookupError):
        propose("SYN-NOPE", "heavy_rain")

    postbooking.cancel_confirm(booking_id, 10)
    with pytest.raises(ValueError):
        propose(booking_id, "heavy_rain")  # a cancelled booking cannot be changed