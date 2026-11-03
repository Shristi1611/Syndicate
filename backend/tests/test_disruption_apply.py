import pytest

from app import bookings, disruptions, postbooking
from app.bookings import confirm_quote, create_quote
from app.config import settings
from app.disruptions import apply_option, propose
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


def by_id(proposal):
    return {option["option_id"]: option for option in proposal["options"]}


def test_cancel_transfers_lowers_the_total():
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    result = apply_option(booking_id, proposal["proposal_id"], "cancel_transfers")

    assert result["old_total"] == 39700
    assert result["new_total"] == 35440
    assert result["cost_delta"] == -4260
    assert result["within_budget"] is True

    booking = bookings.get_booking(booking_id)
    assert booking["total"] == 35440
    assert len(booking["voucher"]["items"]) == 4


def test_rain_cancels_only_the_outdoor_item():
    booking_id, _ = book()
    proposal = propose(booking_id, "heavy_rain")
    result = apply_option(booking_id, proposal["proposal_id"], "cancel_affected")

    assert result["cost_delta"] == -5940
    names = [i["name"] for i in bookings.get_booking(booking_id)["voucher"]["items"]]
    assert "Sunset Beach Dinner" not in names
    assert len(names) == 4


def test_moving_hotel_swaps_it_and_frees_the_old_rooms():
    booking_id, trip = book()
    proposal = propose(booking_id, "hotel_overbooked")
    option = by_id(proposal)["move:H_GOA_04"]
    result = apply_option(booking_id, proposal["proposal_id"], "move:H_GOA_04")

    assert result["cost_delta"] == option["cost_delta"]
    assert result["new_total"] == 39700 + option["cost_delta"]

    booking = bookings.get_booking(booking_id)
    names = [i["name"] for i in booking["voucher"]["items"]]
    assert "Coastline Grand" in names
    assert "Palm Cove Resort" not in names
    assert booking["total"] == result["new_total"]

    # The old hotel's room is free again: all 6 Palm Cove rooms can now be booked.
    for _ in range(6):
        book()
    with pytest.raises(ValueError):
        create_quote(trip)


def test_applying_twice_is_safe():
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    pid = proposal["proposal_id"]

    first = apply_option(booking_id, pid, "cancel_transfers")
    second = apply_option(booking_id, pid, "cancel_transfers")
    assert first["already_applied"] is False
    assert second["already_applied"] is True
    assert second["new_total"] == first["new_total"] == 35440  # charged once, not twice

    with pytest.raises(ValueError):
        apply_option(booking_id, pid, "reschedule")  # a different answer to a resolved disruption


def test_extra_night_adds_a_line_at_the_negotiated_price():
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    option = by_id(proposal)["reschedule_extra_night"]
    result = apply_option(booking_id, proposal["proposal_id"], "reschedule_extra_night")

    assert result["cost_delta"] == option["cost_delta"] > 0
    items = bookings.get_booking(booking_id)["voucher"]["items"]
    assert len(items) == 6
    assert items[-1]["name"] == "Extra night: Palm Cove Resort"

    # A stay with extra nights is handed to a human instead of being moved automatically.
    with pytest.raises(ValueError, match="human"):
        propose(booking_id, "hotel_overbooked")


def test_unknown_proposal_option_and_wrong_booking():
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    pid = proposal["proposal_id"]

    with pytest.raises(LookupError):
        apply_option(booking_id, "P-NOPE", "reschedule")
    with pytest.raises(LookupError):
        apply_option("SYN-OTHER", pid, "reschedule")  # a proposal cannot be used on another booking
    with pytest.raises(ValueError):
        apply_option(booking_id, pid, "free_money")


def test_expired_proposal_is_refused(monkeypatch):
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    monkeypatch.setattr(disruptions, "PROPOSAL_TTL_SECONDS", -1)
    with pytest.raises(ValueError, match="expired"):
        apply_option(booking_id, proposal["proposal_id"], "cancel_transfers")


def test_stale_option_is_refused():
    booking_id, _ = book()
    first = propose(booking_id, "flight_cancelled")
    second = propose(booking_id, "flight_cancelled")

    apply_option(booking_id, first["proposal_id"], "cancel_transfers")
    with pytest.raises(ValueError, match="no longer applies"):
        apply_option(booking_id, second["proposal_id"], "cancel_transfers")


def test_cancelling_after_a_change_refunds_the_new_total():
    booking_id, _ = book()
    proposal = propose(booking_id, "flight_cancelled")
    apply_option(booking_id, proposal["proposal_id"], "cancel_transfers")

    done = postbooking.cancel_confirm(booking_id, 10)  # well before every free-cancellation window
    assert done["refund"] == 35440