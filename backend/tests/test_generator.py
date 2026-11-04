import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import generate_catalogue

BACKEND = Path(__file__).resolve().parents[1]
CATEGORIES = {"sightseeing", "dining", "adventure", "transfer", "wellness", "culture", "nature"}


@pytest.fixture(scope="module")
def data():
    return generate_catalogue.build(seed=2026)


def test_generation_is_deterministic():
    assert generate_catalogue.build(2026) == generate_catalogue.build(2026)
    assert generate_catalogue.build(2026) != generate_catalogue.build(7)


def test_catalogue_shape(data):
    assert len(data["destinations"]) == 16
    assert len(data["suppliers"]) == 18

    for dest in data["destinations"]:
        hotels = [h for h in data["hotels"] if h["destination"] == dest["name"]]
        activities = [a for a in data["activities"] if a["destination"] == dest["name"]]
        assert 8 <= len(hotels) <= 10, dest["name"]
        assert len(activities) == 9, dest["name"]  # 6 signature + 2 generic + 1 transfer


def test_every_item_is_consistent(data):
    supplier_ids = {s["id"] for s in data["suppliers"]}
    suppliers = {s["id"]: s for s in data["suppliers"]}

    ids = [i["id"] for i in data["hotels"] + data["activities"]]
    assert len(ids) == len(set(ids))
    names = [h["name"] for h in data["hotels"]]
    assert len(names) == len(set(names))

    for hotel in data["hotels"]:
        assert hotel["supplier_id"] in supplier_ids
        assert 2 <= hotel["star"] <= 5
        assert hotel["rooms_available"] > 0
        price = hotel["list_price_per_night"]
        assert round(price * suppliers[hotel["supplier_id"]]["floor_ratio"]) < price

    for activity in data["activities"]:
        assert activity["supplier_id"] in supplier_ids
        assert activity["category"] in CATEGORIES
        price = activity["list_price_per_person"]
        assert round(price * suppliers[activity["supplier_id"]]["floor_ratio"]) < price

    for supplier in data["suppliers"]:
        assert supplier["tradeable"]
        assert 0.7 <= supplier["floor_ratio"] < 1


def test_every_destination_is_usable(data):
    for dest in data["destinations"]:
        name = dest["name"]
        hotels = [h for h in data["hotels"] if h["destination"] == name]
        activities = [a for a in data["activities"] if a["destination"] == name]

        step_free = [h for h in hotels if h["stairs_free"]]
        assert len(step_free) >= 3, name
        assert any("family" in h["tags"] for h in step_free), name

        assert len([a for a in activities if a["category"] == "transfer"]) == 1, name
        easy = [a for a in activities if a["category"] != "transfer" and a["stairs_free"]]
        assert len(easy) >= 3, name


def test_personas_plan_well_on_the_big_catalogue(data, tmp_path):
    """Load the generated data in a fresh process and plan every persona against it."""
    generate_catalogue.write(tmp_path, data)

    code = """
import json
from app.inventory import get_item
from app.personas import list_personas
from app.planner import plan_trip

out = {}
for persona in list_personas():
    plan = plan_trip(persona["profile"])
    out[persona["id"]] = {
        "hotel": plan["items"][0]["item_id"],
        "within_budget": plan["within_budget"],
        "notes": plan["notes"],
        "total": plan["list_total"],
        "all_step_free": all(get_item(i["item_id"])["stairs_free"] for i in plan["items"]),
    }
print(json.dumps(out))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, "CATALOGUE_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    plans = json.loads(result.stdout)

    for persona_id, plan in plans.items():
        assert plan["within_budget"] is True, persona_id
        assert plan["notes"] == [], persona_id

    hotels = {plan["hotel"] for plan in plans.values()}
    assert len(hotels) == 3  # three personas, three different hotels
    assert plans["family"]["all_step_free"] is True
    assert plans["backpacker"]["total"] == min(p["total"] for p in plans.values())