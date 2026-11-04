import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import generate_catalogue
import generate_flights

BACKEND = Path(__file__).resolve().parents[1]
HUB_NAMES = {"Delhi", "Kolkata", "Mumbai"}


# ------------------------------------------------------------ the generator


@pytest.fixture(scope="module")
def world():
    data = generate_catalogue.build(2026)
    flights = generate_flights.build_flights(data["destinations"], 2026)
    return data, flights


def routes_of(flights):
    routes = {}
    for flight in flights:
        routes.setdefault((flight["origin"], flight["destination"]), []).append(flight)
    return routes


def test_flight_generation_is_deterministic(world):
    data, flights = world
    assert generate_flights.build_flights(data["destinations"], 2026) == flights
    assert generate_flights.build_flights(data["destinations"], 7) != flights


def test_routes_start_at_hubs(world):
    _, flights = world
    routes = routes_of(flights)

    assert {origin for origin, _ in routes} == HUB_NAMES
    for (origin, destination), options in routes.items():
        assert origin != destination
        assert 2 <= len(options) <= 3
    for hub in HUB_NAMES:
        assert len([1 for (origin, _) in routes if origin == hub]) >= 11

    assert ("Delhi", "Goa") in routes
    assert ("Delhi", "Leh") in routes
    assert ("Delhi", "Agra") not in routes  # too close to fly


def test_flights_are_consistent(world):
    data, flights = world
    airlines = {s["id"]: s for s in generate_flights.AIRLINE_SUPPLIERS}

    assert not set(airlines) & {s["id"] for s in data["suppliers"]}  # no clashing ids
    ids = [f["id"] for f in flights]
    assert len(ids) == len(set(ids))

    for flight in flights:
        assert flight["category"] == "flight"
        assert flight["supplier_id"] in airlines
        assert flight["airline"] == airlines[flight["supplier_id"]]["name"]
        assert flight["stops"] in (0, 1)
        assert 45 <= flight["duration_minutes"] <= 600
        price = flight["list_price_per_person"]
        assert price > 0
        assert round(price * airlines[flight["supplier_id"]]["floor_ratio"]) < price

    for airline in airlines.values():
        assert airline["tradeable"]
        assert 0.7 <= airline["floor_ratio"] < 1


def test_adding_flights_is_repeatable(tmp_path):
    generate_catalogue.write(tmp_path, generate_catalogue.build(2026))
    first = generate_flights.add_to_catalogue(tmp_path, 2026)
    second = generate_flights.add_to_catalogue(tmp_path, 2026)
    assert first == second > 0

    suppliers = json.loads((tmp_path / "suppliers.json").read_text(encoding="utf-8"))
    assert len(suppliers) == 22  # 18 hotel and experience suppliers + 4 airlines
    assert len({s["id"] for s in suppliers}) == 22

    flights = json.loads((tmp_path / "flights.json").read_text(encoding="utf-8"))
    assert len(flights) == first


# ------------------------------------------ the small test catalogue (no flights)


def test_small_catalogue_has_no_flights():
    from app.inventory import FLIGHTS, HUBS

    assert FLIGHTS == {}
    assert HUBS == []


def test_flights_are_refused_without_flight_data():
    from app.planner import plan_trip

    profile = {"destination": "Goa", "origin": "Delhi", "nights": 3, "travellers": 2, "budget_total": 80000}
    with pytest.raises(ValueError, match="not available"):
        plan_trip(profile)


# ------------------------------------- the big catalogue (runs in its own process)


@pytest.fixture(scope="module")
def big_catalogue(tmp_path_factory):
    folder = tmp_path_factory.mktemp("catalogue")
    generate_catalogue.write(folder, generate_catalogue.build(2026))
    generate_flights.add_to_catalogue(folder, 2026)
    return folder


def run(code: str, catalogue: Path, **env) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, "CATALOGUE_DIR": str(catalogue), "LLM_PROVIDER": "mock", **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_plan_includes_round_trip_flights(big_catalogue):
    out = run(
        """
import json
from app.inventory import get_item
from app.planner import plan_trip

profile = {"destination": "Goa", "origin": "Delhi", "nights": 4, "travellers": 3,
           "budget_total": 150000, "stairs_free": True, "interests": ["quiet"]}
plan = plan_trip(profile)
flight = plan["items"][1]
item = get_item(flight["item_id"])
print(json.dumps({
    "categories": [i["category"] for i in plan["items"]],
    "flight_quantity": flight["quantity"],
    "flight_unit": flight["unit"],
    "route": [item["origin"], item["destination"]],
    "list_total": plan["list_total"],
    "sum_of_lines": sum(i["total"] for i in plan["items"]),
    "within_budget": plan["within_budget"],
    "notes": plan["notes"],
}))
""",
        big_catalogue,
    )
    assert out["categories"][0] == "hotel"
    assert out["categories"][1] == "flight"
    assert "transfer" in out["categories"]
    assert out["flight_quantity"] == 6  # 3 people, out and back
    assert out["flight_unit"] == "person-trip"
    assert out["route"] == ["Delhi", "Goa"]
    assert out["list_total"] == out["sum_of_lines"]
    assert out["within_budget"] is True
    assert out["notes"] == []


def test_route_without_flights_gets_a_note(big_catalogue):
    out = run(
        """
import json
from app.planner import plan_trip

profile = {"destination": "Agra", "origin": "Delhi", "nights": 2, "travellers": 2, "budget_total": 60000}
plan = plan_trip(profile)
print(json.dumps({"categories": [i["category"] for i in plan["items"]], "notes": plan["notes"]}))
""",
        big_catalogue,
    )
    assert "flight" not in out["categories"]
    assert any("no flights" in note.lower() for note in out["notes"])


def test_bad_origins_are_refused(big_catalogue):
    out = run(
        """
import json
from app.planner import plan_trip

base = {"destination": "Jaipur", "nights": 3, "travellers": 2, "budget_total": 90000}

def attempt(profile):
    try:
        plan_trip(profile)
        return None
    except ValueError as exc:
        return str(exc)

print(json.dumps({
    "not_a_hub": attempt({**base, "origin": "Goa"}),
    "same_city": attempt({**base, "destination": "Delhi", "origin": "Delhi"}),
}))
""",
        big_catalogue,
    )
    assert "Kolkata" in out["not_a_hub"]  # the message lists the cities flights can leave from
    assert "same" in out["same_city"].lower()


@pytest.fixture(scope="module")
def chat_results(big_catalogue):
    return run(
        """
import json
from app.chat import apply_updates, chat_turn
from app.profile import TravellerProfile

full = chat_turn("Goa, 4 nights, 3 people, Rs 120k, flying from Delhi", {})
reverse = chat_turn("Delhi, 3 nights, 2 people, Rs 90k, from Mumbai", {})
plain = chat_turn("Goa, 4 nights, 3 people, Rs 120k", {})
cleared = chat_turn("Delhi please", {"destination": "Goa", "origin": "Delhi"})
rejected = apply_updates(TravellerProfile(destination="Goa"), {"origin": "Jaipur"})

print(json.dumps({
    "full": full,
    "reverse": reverse["profile"],
    "plain": plain,
    "cleared": cleared["profile"],
    "rejected_origin": rejected.origin,
}))
""",
        big_catalogue,
    )


def test_chat_reads_flying_from(chat_results):
    profile = chat_results["full"]["profile"]
    assert profile["origin"] == "Delhi"
    assert profile["destination"] == "Goa"
    assert chat_results["full"]["complete"] is True
    assert "flying from" not in chat_results["full"]["reply"]  # already told us


def test_chat_reads_origin_and_destination_together(chat_results):
    assert chat_results["reverse"]["origin"] == "Mumbai"
    assert chat_results["reverse"]["destination"] == "Delhi"


def test_chat_offers_flights_when_origin_is_missing(chat_results):
    assert chat_results["plain"]["complete"] is True
    assert "flying from" in chat_results["plain"]["reply"]
    assert "Kolkata" in chat_results["plain"]["reply"]


def test_changing_destination_to_the_origin_clears_it(chat_results):
    assert chat_results["cleared"]["destination"] == "Delhi"
    assert chat_results["cleared"]["origin"] is None


def test_a_non_hub_origin_is_ignored(chat_results):
    assert chat_results["rejected_origin"] is None


def test_flight_trip_negotiates_books_and_rejects_tampering(big_catalogue, tmp_path):
    out = run(
        """
import json
import os
from pathlib import Path

from app import bookings

bookings.DB_PATH = Path(os.environ["TEST_DB"])  # never touch the real bookings
bookings._init()

from app.bookings import confirm_quote, create_quote
from app.inventory import floor_price, get_item
from app.trip import negotiate_plan

profile = {"destination": "Goa", "origin": "Delhi", "nights": 4, "travellers": 3,
           "budget_total": 150000, "stairs_free": True, "interests": ["quiet"]}
trip = negotiate_plan(profile)
flight = next(line for line in trip["items"] if line["category"] == "flight")
floor = floor_price(get_item(flight["item_id"]))

booking = confirm_quote(create_quote(trip)["quote_id"])

tampered = json.loads(json.dumps(trip))
next(line for line in tampered["items"] if line["category"] == "flight")["final_unit_price"] = 1
try:
    create_quote(tampered)
    error = None
except ValueError as exc:
    error = str(exc)

print(json.dumps({
    "flight_name": flight["name"],
    "flight_unit": flight["unit_price"],
    "flight_final": flight["final_unit_price"],
    "flight_floor": floor,
    "flight_saved": flight["saved"],
    "status": booking["status"],
    "voucher_names": [i["name"] for i in booking["voucher"]["items"]],
    "tamper_error": error,
}))
""",
        big_catalogue,
        TEST_DB=str(tmp_path / "trip.db"),
    )
    assert out["flight_saved"] > 0
    assert out["flight_floor"] <= out["flight_final"] < out["flight_unit"]
    assert out["status"] == "confirmed"
    assert out["flight_name"] in out["voucher_names"]
    assert "floor" in out["tamper_error"]