import pytest
from fastapi.testclient import TestClient

from app import bookings
from app.bookings import confirm_quote, create_quote
from app.chat import chat_turn
from app.config import settings
from app.main import app
from app.planner import plan_trip
from app.trip import negotiate_plan

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
    """Fresh empty database and the free mock model for every test."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def test_swapping_the_hotel_changes_the_plan():
    default = plan_trip(PROFILE)
    assert default["items"][0]["item_id"] == "H_GOA_01"

    swapped = plan_trip({**PROFILE, "hotel_id": "H_GOA_04"})
    assert swapped["items"][0]["item_id"] == "H_GOA_04"
    assert swapped["items"][0]["name"] == "Coastline Grand"
    assert swapped["items"][0]["quantity"] == 4
    assert swapped["within_budget"] is True


def test_cannot_swap_to_a_hotel_with_stairs_when_step_free_is_needed():
    with pytest.raises(ValueError, match="step-free"):
        plan_trip({**PROFILE, "hotel_id": "H_GOA_02"})


def test_cannot_swap_to_a_hotel_in_another_city():
    with pytest.raises(ValueError, match="not in Goa"):
        plan_trip({**PROFILE, "hotel_id": "H_JAI_01"})


def test_unknown_hotel_is_refused():
    with pytest.raises(ValueError, match="Unknown hotel"):
        plan_trip({**PROFILE, "hotel_id": "H_NOPE"})


def test_swap_needs_enough_rooms():
    big_party = {**PROFILE, "travellers": 15, "stairs_free": False, "budget_total": 300000}
    with pytest.raises(ValueError, match="only 4 room"):
        plan_trip({**big_party, "hotel_id": "H_GOA_03"})  # 5 rooms needed, the villa has 4


def test_a_swapped_trip_negotiates_and_books():
    trip = negotiate_plan({**PROFILE, "hotel_id": "H_GOA_04"})
    assert trip["items"][0]["name"] == "Coastline Grand"
    assert trip["saved"] > 0

    quote = create_quote(trip)
    booking = confirm_quote(quote["quote_id"])
    assert booking["status"] == "confirmed"
    assert booking["voucher"]["items"][0]["name"] == "Coastline Grand"


def test_changing_destination_clears_the_swapped_hotel():
    profile = {**PROFILE, "hotel_id": "H_GOA_04"}
    moved = chat_turn("Jaipur please", profile)["profile"]
    assert moved["destination"] == "Jaipur"
    assert moved["hotel_id"] is None


def test_keeping_the_destination_keeps_the_swapped_hotel():
    profile = {**PROFILE, "hotel_id": "H_GOA_04"}
    same = chat_turn("Goa again", profile)["profile"]
    assert same["hotel_id"] == "H_GOA_04"


def test_hotels_endpoint_is_public_and_filtered():
    goa = client.get("/hotels", params={"destination": "Goa"})
    assert goa.status_code == 200
    assert len(goa.json()) == 4
    assert len(client.get("/hotels").json()) == 8

    # Only these public fields may ever be returned. Anything else, like a floor price
    # or a supplier id, would make this test fail.
    allowed = {"id", "name", "destination", "star", "tags", "stairs_free", "list_price"}
    for hotel in client.get("/hotels").json():
        assert set(hotel) == allowed

    text = client.get("/hotels").text.lower()
    assert "floor_ratio" not in text
    assert "floor_price" not in text
    assert "supplier" not in text