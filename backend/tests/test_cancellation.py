import pytest

from app import bookings, postbooking
from app.bookings import confirm_quote, create_quote
from app.config import settings
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
    quote = create_quote(trip)
    return confirm_quote(quote["quote_id"])["booking_id"], trip


def test_preview_changes_nothing():
    booking_id, _ = book()
    preview = postbooking.cancel_preview(booking_id, 10)
    assert preview["refund"] == 39700
    assert preview["fee"] == 0
    assert preview["requires_confirmation"] is True
    assert bookings.get_booking(booking_id)["status"] == "confirmed"


def test_late_cancellation_keeps_half():
    booking_id, _ = book()
    preview = postbooking.cancel_preview(booking_id, 3)  # inside every supplier's free window
    assert preview["refund"] == 19850
    assert preview["fee"] == 19850


def test_mixed_windows_are_charged_per_item():
    booking_id, _ = book()
    # 4 days: Trailhead (free until 4 days) refunds fully, Palm Group (free until 5) keeps half.
    preview = postbooking.cancel_preview(booking_id, 4)
    assert preview["refund"] == 23540
    free = {line["name"]: line["free_cancellation"] for line in preview["lines"]}
    assert free["Palm Cove Resort"] is False
    assert free["Old Goa Heritage Walk"] is True


def test_cancel_is_safe_to_repeat():
    booking_id, _ = book()
    first = postbooking.cancel_confirm(booking_id, 10)
    assert first["status"] == "cancelled"
    assert first["refund"] == 39700
    assert first["already_cancelled"] is False

    second = postbooking.cancel_confirm(booking_id, 10)
    assert second["already_cancelled"] is True
    assert second["refund"] == 39700  # the same refund, paid out once
    assert bookings.get_booking(booking_id)["status"] == "cancelled"


def test_cancelled_booking_cannot_be_previewed_again():
    booking_id, _ = book()
    postbooking.cancel_confirm(booking_id, 10)
    with pytest.raises(ValueError):
        postbooking.cancel_preview(booking_id, 10)


def test_cancelling_frees_the_room():
    ids = [book()[0] for _ in range(6)]  # Palm Cove Resort has 6 rooms: now sold out
    trip = negotiate_plan(PROFILE)
    with pytest.raises(ValueError):
        create_quote(trip)

    postbooking.cancel_confirm(ids[0], 10)
    assert create_quote(trip)["quote_id"]  # one room is free again


def test_bad_input_is_rejected():
    booking_id, _ = book()
    with pytest.raises(ValueError):
        postbooking.cancel_preview(booking_id, -1)
    with pytest.raises(LookupError):
        postbooking.cancel_preview("SYN-NOPE", 5)