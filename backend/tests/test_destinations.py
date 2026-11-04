import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import generate_catalogue

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def big_catalogue(tmp_path_factory):
    folder = tmp_path_factory.mktemp("catalogue")
    generate_catalogue.write(folder, generate_catalogue.build(2026))
    return folder


def run(code: str, catalogue: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, "CATALOGUE_DIR": str(catalogue), "LLM_PROVIDER": "mock"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_all_sixteen_cities_are_choosable(big_catalogue):
    out = run(
        """
import json
from app.chat import chat_turn
from app.inventory import DESTINATIONS

picked = {}
for city in DESTINATIONS:
    reply = chat_turn(f"{city}, 3 nights, 2 people, Rs 90k", {})
    picked[city] = reply["profile"]["destination"]
print(json.dumps(picked))
""",
        big_catalogue,
    )
    assert len(out) == 16
    assert all(name == picked for name, picked in out.items())


def test_every_city_plans_a_valid_trip(big_catalogue):
    out = run(
        """
import json
from app.inventory import DESTINATIONS, get_item
from app.planner import plan_trip

results = {}
for city in DESTINATIONS:
    profile = {"destination": city, "nights": 3, "travellers": 3, "budget_total": 120000,
               "stairs_free": True, "interests": ["family", "quiet"]}
    plan = plan_trip(profile)
    results[city] = {
        "items": len(plan["items"]),
        "within_budget": plan["within_budget"],
        "step_free": all(get_item(i["item_id"])["stairs_free"] for i in plan["items"]),
        "same_city": all(get_item(i["item_id"])["destination"] == city for i in plan["items"]),
    }
print(json.dumps(results))
""",
        big_catalogue,
    )
    assert len(out) == 16
    for city, r in out.items():
        assert r["items"] >= 3, city
        assert r["within_budget"] is True, city
        assert r["step_free"] is True, city
        assert r["same_city"] is True, city


def test_the_question_lists_the_cities(big_catalogue):
    out = run(
        """
import json
from app.chat import chat_turn
print(json.dumps({"reply": chat_turn("hello", {})["reply"]}))
""",
        big_catalogue,
    )
    assert "Kerala" in out["reply"]
    assert "Andaman" in out["reply"]


def test_destinations_endpoint(big_catalogue):
    out = run(
        """
import json
from fastapi.testclient import TestClient
from app.main import app

body = TestClient(app).get("/destinations").json()
print(json.dumps({"count": len(body), "keys": sorted(body[0])}))
""",
        big_catalogue,
    )
    assert out["count"] == 16
    assert {"name", "region", "tagline", "lat", "lon"} <= set(out["keys"])