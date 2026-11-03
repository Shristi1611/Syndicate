from fastapi.testclient import TestClient

from app.inventory import get_item
from app.main import app
from app.personas import list_personas
from app.planner import plan_trip

client = TestClient(app)


def plans() -> dict:
    return {p["id"]: plan_trip(p["profile"]) for p in list_personas()}


def test_three_personas_load():
    assert {p["id"] for p in list_personas()} == {"honeymoon", "family", "backpacker"}


def test_each_persona_plans_within_budget():
    for plan in plans().values():
        assert plan["within_budget"] is True
        assert plan["notes"] == []  # a hotel fit comfortably, no "cheapest option" fallback


def test_personas_get_different_hotels():
    hotels = {pid: plan["items"][0]["name"] for pid, plan in plans().items()}
    assert hotels == {
        "honeymoon": "Coastline Grand",
        "family": "Palm Cove Resort",
        "backpacker": "Baga Breeze Hotel",
    }


def test_family_trip_is_step_free():
    for item in plans()["family"]["items"]:
        assert get_item(item["item_id"])["stairs_free"] is True


def test_backpacker_trip_is_the_cheapest():
    totals = {pid: plan["list_total"] for pid, plan in plans().items()}
    assert totals["backpacker"] == min(totals.values())


def test_persona_endpoints():
    res = client.get("/personas")
    assert res.status_code == 200
    assert len(res.json()) == 3

    family = client.get("/personas/family")
    assert family.status_code == 200
    assert family.json()["profile"]["travellers"] == 5

    assert client.get("/personas/nobody").status_code == 404