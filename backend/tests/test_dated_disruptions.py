import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import generate_catalogue
import generate_flights
from app import bookings, seasons
from app.bookings import confirm_quote, create_quote, get_booking
from app.config import settings
from app.disruptions import apply_option, propose
from app.inventory import floor_price, get_item, list_price
from app.main import app
from app.trip import negotiate_plan

BACKEND = Path(__file__).resolve().parents[1]
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
UNDATED = {key: value for key, value in PEAK.items() if key != "start_date"}

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Fresh empty database and the free mock model for every test."""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(bookings, "DB_PATH", tmp_path / "test.db")
    bookings._init()


def book(profile):
    trip = negotiate_plan(profile)
    return confirm_quote(create_quote(trip)["quote_id"])["booking_id"], trip


# ------------------------------------------------ the small test catalogue


def test_a_peak_hotel_swap_is_priced_and_guarded_for_the_dates():
    booking_id, trip = book(PEAK)
    old = trip["items"][0]
    proposal = propose(booking_id, "hotel_overbooked")
    move = next(o for o in proposal["options"] if o["option_id"].startswith("move:"))
    alt = get_item(move["option_id"].split(":", 1)[1])

    listed = seasons.adjust(list_price(alt), seasons.hotel_factor("Goa", START, 4))
    assert listed > list_price(alt)  # peak season costs more than the year-round list price
    assert move["list_price"] == listed
    assert floor_price(alt, listed) <= move["new_unit_price"] <= listed
    assert move["cost_delta"] == move["new_unit_price"] * old["quantity"] - old["final_total"]

    result = apply_option(booking_id, proposal["proposal_id"], move["option_id"])
    assert result["cost_delta"] == move["cost_delta"]

    first = get_booking(booking_id)["voucher"]["items"][0]
    assert first["name"] == alt["name"]
    assert first["final_unit_price"] == move["new_unit_price"]


def test_an_extra_night_is_priced_at_the_trips_seasonal_rate():
    booking_id, trip = book(PEAK)
    hotel = trip["items"][0]
    item = get_item(hotel["item_id"])
    rooms = hotel["quantity"] // PEAK["nights"]

    proposal = propose(booking_id, "flight_cancelled")
    option = next(o for o in proposal["options"] if o["option_id"] == "reschedule_extra_night")

    assert option["list_price"] == hotel["unit_price"] > list_price(item)
    assert floor_price(item, hotel["unit_price"]) <= option["new_unit_price"] <= hotel["unit_price"]
    assert option["new_unit_price"] > list_price(item)  # dearer than a year-round night
    assert option["cost_delta"] == option["new_unit_price"] * rooms

    result = apply_option(booking_id, proposal["proposal_id"], "reschedule_extra_night")
    assert result["cost_delta"] == option["cost_delta"]

    extra = get_booking(booking_id)["voucher"]["items"][-1]
    assert extra["name"].startswith("Extra night")
    assert extra["final_unit_price"] == option["new_unit_price"]


def test_undated_disruptions_keep_year_round_prices():
    booking_id, trip = book(UNDATED)
    item = get_item(trip["items"][0]["item_id"])

    extra = next(
        o for o in propose(booking_id, "flight_cancelled")["options"]
        if o["option_id"] == "reschedule_extra_night"
    )
    assert extra["list_price"] == list_price(item)

    move = next(
        o for o in propose(booking_id, "hotel_overbooked")["options"]
        if o["option_id"].startswith("move:")
    )
    alt = get_item(move["option_id"].split(":", 1)[1])
    assert move["list_price"] == list_price(alt)


def test_calendar_for_every_destination():
    for city in seasons.MONTHLY:
        calendar = seasons.calendar(city)
        assert calendar["destination"] == city
        assert [m["month"] for m in calendar["months"]] == list(range(1, 13))

        factors = {m["name"]: m["factor"] for m in calendar["months"]}
        assert factors[calendar["cheapest_month"]] == min(factors.values())
        assert factors[calendar["busiest_month"]] == max(factors.values())

    names = {event["name"] for event in seasons.calendar("Goa")["events"]}
    assert "Year-end holidays" in names


def test_seasons_endpoint():
    res = client.get("/seasons/Goa")
    assert res.status_code == 200
    body = res.json()
    assert body["destination"] == "Goa"
    assert len(body["months"]) == 12
    assert body["cheapest_month"] == "July"
    assert body["busiest_month"] == "December"
    assert body["weekend_premium_pct"] == 10

    assert client.get("/seasons/Atlantis").status_code == 404


# ------------------------------- the big catalogue (runs in its own process)

PRELUDE = """
import json
import os
from datetime import date
from pathlib import Path

from app import bookings, seasons

bookings.DB_PATH = Path(os.environ["TEST_DB"])  # never touch the real bookings
bookings._init()

from app.bookings import confirm_quote, create_quote, get_booking
from app.disruptions import apply_option, propose
from app.inventory import FLIGHTS, floor_price, list_price
from app.trip import negotiate_plan

PROFILE = {"destination": "Goa", "origin": "Delhi", "start_date": "2026-12-20", "nights": 4,
           "travellers": 3, "budget_total": 200000, "stairs_free": True, "interests": ["quiet"]}
trip = negotiate_plan(PROFILE)
booking_id = confirm_quote(create_quote(trip)["quote_id"])["booking_id"]
flight = next(line for line in trip["items"] if line["category"] == "flight")
"""


@pytest.fixture(scope="module")
def big_catalogue(tmp_path_factory):
    folder = tmp_path_factory.mktemp("catalogue")
    generate_catalogue.write(folder, generate_catalogue.build(2026))
    generate_flights.add_to_catalogue(folder, 2026)
    return folder


def run(code: str, catalogue: Path, tmp_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", PRELUDE + code],
        cwd=BACKEND,
        env={
            **os.environ,
            "CATALOGUE_DIR": str(catalogue),
            "LLM_PROVIDER": "mock",
            "TEST_DB": str(tmp_path / "trip.db"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_dated_flight_rebooking_uses_the_seasonal_fare(big_catalogue, tmp_path):
    out = run(
        """
proposal = propose(booking_id, "flight_cancelled")
factor = seasons.flight_factor("Goa", date(2026, 12, 20), 4)

rebooks = []
for option in proposal["options"]:
    if not option["option_id"].startswith("rebook:"):
        continue
    alt = FLIGHTS[option["option_id"].split(":", 1)[1]]
    listed = seasons.adjust(list_price(alt), factor)
    rebooks.append({
        "option_id": option["option_id"],
        "name": alt["name"],
        "listed": listed,
        "year_round": list_price(alt),
        "option_list": option["list_price"],
        "new_unit": option["new_unit_price"],
        "floor": floor_price(alt, listed),
        "delta": option["cost_delta"],
        "expected_delta": option["new_unit_price"] * flight["quantity"] - flight["final_total"],
    })

first = rebooks[0]
before = get_booking(booking_id)["total"]
result = apply_option(booking_id, proposal["proposal_id"], first["option_id"])
after = get_booking(booking_id)
new_line = next(i for i in after["voucher"]["items"] if i["name"] == first["name"])

print(json.dumps({
    "rebooks": rebooks,
    "before": before,
    "after": after["total"],
    "result_delta": result["cost_delta"],
    "new_final_unit": new_line["final_unit_price"],
}))
""",
        big_catalogue,
        tmp_path,
    )
    assert len(out["rebooks"]) >= 1
    for rebook in out["rebooks"]:
        assert rebook["listed"] > rebook["year_round"]  # peak-season fare
        assert rebook["option_list"] == rebook["listed"]
        assert rebook["floor"] <= rebook["new_unit"] <= rebook["listed"]
        assert rebook["delta"] == rebook["expected_delta"]

    first = out["rebooks"][0]
    assert out["result_delta"] == first["delta"]
    assert out["after"] == out["before"] + first["delta"]
    assert out["new_final_unit"] == first["new_unit"]