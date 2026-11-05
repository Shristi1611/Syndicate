import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import generate_catalogue
import generate_flights

BACKEND = Path(__file__).resolve().parents[1]

PRELUDE = """
import json
import os
from pathlib import Path

from app import bookings

bookings.DB_PATH = Path(os.environ["TEST_DB"])  # never touch the real bookings
bookings._init()

from app.bookings import confirm_quote, create_quote, get_booking
from app.disruptions import apply_option, propose
from app.inventory import FLIGHTS, floor_price, get_item, list_price
from app.postbooking import cancel_confirm
from app.trip import negotiate_plan

PROFILE = {"destination": "Goa", "origin": "Delhi", "nights": 4, "travellers": 3,
           "budget_total": 150000, "stairs_free": True, "interests": ["quiet"]}
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


def test_proposal_offers_other_flights_or_a_refund(big_catalogue, tmp_path):
    out = run(
        """
proposal = propose(booking_id, "flight_cancelled")
options = {o["option_id"]: o for o in proposal["options"]}
current = get_item(flight["item_id"])

rebooks = []
for option_id, option in options.items():
    if not option_id.startswith("rebook:"):
        continue
    alt = FLIGHTS[option_id.split(":", 1)[1]]
    rebooks.append({
        "id": alt["id"],
        "same_route": [alt["origin"], alt["destination"]] == [current["origin"], current["destination"]],
        "new_unit": option["new_unit_price"],
        "floor": floor_price(alt),
        "list": list_price(alt),
        "delta": option["cost_delta"],
        "expected_delta": option["new_unit_price"] * flight["quantity"] - flight["final_total"],
    })

print(json.dumps({
    "option_ids": sorted(options),
    "affected": proposal["affected"],
    "flight_name": flight["name"],
    "flight_id": flight["item_id"],
    "flight_final_total": flight["final_total"],
    "cancel_delta": options["cancel_flight"]["cost_delta"],
    "rebooks": rebooks,
}))
""",
        big_catalogue,
        tmp_path,
    )
    assert "cancel_flight" in out["option_ids"]
    assert not {"reschedule", "reschedule_extra_night", "cancel_transfers"} & set(out["option_ids"])
    assert out["affected"] == [out["flight_name"]]
    assert out["cancel_delta"] == -out["flight_final_total"]

    assert 1 <= len(out["rebooks"]) <= 2
    for rebook in out["rebooks"]:
        assert rebook["same_route"] is True
        assert rebook["id"] != out["flight_id"]
        assert rebook["floor"] <= rebook["new_unit"] <= rebook["list"]
        assert rebook["delta"] == rebook["expected_delta"]


def test_rebooking_swaps_the_flight_and_is_safe_to_repeat(big_catalogue, tmp_path):
    out = run(
        """
proposal = propose(booking_id, "flight_cancelled")
option = next(o for o in proposal["options"] if o["option_id"].startswith("rebook:"))
new_flight = FLIGHTS[option["option_id"].split(":", 1)[1]]

before = get_booking(booking_id)
first = apply_option(booking_id, proposal["proposal_id"], option["option_id"])
again = apply_option(booking_id, proposal["proposal_id"], option["option_id"])
after = get_booking(booking_id)

names = [i["name"] for i in after["voucher"]["items"]]
new_line = next(i for i in after["voucher"]["items"] if i["name"] == new_flight["name"])
print(json.dumps({
    "old_name": flight["name"],
    "new_name": new_flight["name"],
    "names": names,
    "item_count_before": len(before["voucher"]["items"]),
    "item_count_after": len(names),
    "before_total": before["total"],
    "after_total": after["total"],
    "delta": option["cost_delta"],
    "first_delta": first["cost_delta"],
    "first_new_total": first["new_total"],
    "again_applied": again["already_applied"],
    "again_new_total": again["new_total"],
    "new_quantity": new_line["quantity"],
    "old_quantity": flight["quantity"],
}))
""",
        big_catalogue,
        tmp_path,
    )
    assert out["old_name"] not in out["names"]
    assert out["new_name"] in out["names"]
    assert out["item_count_after"] == out["item_count_before"]
    assert out["new_quantity"] == out["old_quantity"] == 6
    assert out["first_delta"] == out["delta"]
    assert out["after_total"] == out["before_total"] + out["delta"] == out["first_new_total"]
    assert out["again_applied"] is True
    assert out["again_new_total"] == out["after_total"]  # charged once, not twice


def test_cancelling_the_flights_refunds_them(big_catalogue, tmp_path):
    out = run(
        """
proposal = propose(booking_id, "flight_cancelled")
before = get_booking(booking_id)
result = apply_option(booking_id, proposal["proposal_id"], "cancel_flight")
after = get_booking(booking_id)

print(json.dumps({
    "flight_name": flight["name"],
    "flight_final_total": flight["final_total"],
    "before_total": before["total"],
    "after_total": after["total"],
    "delta": result["cost_delta"],
    "names_after": [i["name"] for i in after["voucher"]["items"]],
    "count_before": len(before["voucher"]["items"]),
}))
""",
        big_catalogue,
        tmp_path,
    )
    assert out["flight_name"] not in out["names_after"]
    assert len(out["names_after"]) == out["count_before"] - 1  # hotel, transfer and activities remain
    assert out["delta"] == -out["flight_final_total"]
    assert out["after_total"] == out["before_total"] - out["flight_final_total"]


def test_cancelling_after_a_rebooking_refunds_the_new_total(big_catalogue, tmp_path):
    out = run(
        """
proposal = propose(booking_id, "flight_cancelled")
option = next(o for o in proposal["options"] if o["option_id"].startswith("rebook:"))
changed = apply_option(booking_id, proposal["proposal_id"], option["option_id"])
done = cancel_confirm(booking_id, 30)  # far ahead of every supplier's free-cancellation window
print(json.dumps({"new_total": changed["new_total"], "refund": done["refund"], "fee": done["fee"]}))
""",
        big_catalogue,
        tmp_path,
    )
    assert out["fee"] == 0
    assert out["refund"] == out["new_total"]


def test_unknown_and_stale_options_are_refused(big_catalogue, tmp_path):
    out = run(
        """
first = propose(booking_id, "flight_cancelled")
second = propose(booking_id, "flight_cancelled")  # a second proposal, made before anything changed
option = next(o for o in first["options"] if o["option_id"].startswith("rebook:"))

def attempt(proposal_id, option_id):
    try:
        apply_option(booking_id, proposal_id, option_id)
        return None
    except ValueError as exc:
        return str(exc)

unknown = attempt(first["proposal_id"], "rebook:F_NOPE_NOPE_1")
apply_option(booking_id, first["proposal_id"], option["option_id"])
stale = attempt(second["proposal_id"], option["option_id"])  # that flight is already booked
print(json.dumps({"unknown": unknown, "stale": stale}))
""",
        big_catalogue,
        tmp_path,
    )
    assert "Unknown option" in out["unknown"]
    assert "no longer applies" in out["stale"]


def test_heavy_rain_never_touches_the_flights(big_catalogue, tmp_path):
    out = run(
        """
try:
    proposal = propose(booking_id, "heavy_rain")
    affected = proposal["affected"]
except ValueError:
    affected = []  # nothing outdoors in this trip is also fine
print(json.dumps({"flight_name": flight["name"], "affected": affected}))
""",
        big_catalogue,
        tmp_path,
    )
    assert out["flight_name"] not in out["affected"]