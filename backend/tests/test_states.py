import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import generate_catalogue
from app.main import app
from app.states import CITY_STATE, STATES, state_of, states_with_cities

BACKEND = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_every_generated_city_has_a_state():
    names = [d["name"] for d in generate_catalogue.DESTINATIONS]
    assert len(names) == 16
    for name in names:
        assert state_of(name) in STATES, name  # a new city without a state fails here


def test_there_are_thirteen_states():
    cities = [d["name"] for d in generate_catalogue.DESTINATIONS]
    assert len({state_of(name) for name in cities}) == 13
    assert set(CITY_STATE.values()) == set(STATES)  # no state without a city, no city without a state


def test_state_markers_are_on_india():
    for state, (lat, lon) in STATES.items():
        assert 6 <= lat <= 37, state
        assert 68 <= lon <= 98, state


def test_unmapped_cities_and_empty_states_are_left_out():
    destinations = {"Goa": {"region": "West", "tagline": "Beaches"}, "Atlantis": {"region": "Sea"}}
    result = states_with_cities(destinations)
    assert [state["name"] for state in result] == ["Goa"]  # Atlantis has no state, so it is skipped
    assert result[0]["cities"] == [{"name": "Goa", "region": "West", "tagline": "Beaches"}]


def test_states_endpoint_on_the_small_catalogue():
    body = client.get("/states").json()
    assert [state["name"] for state in body] == ["Goa", "Rajasthan"]
    rajasthan = next(state for state in body if state["name"] == "Rajasthan")
    assert [city["name"] for city in rajasthan["cities"]] == ["Jaipur"]
    assert set(rajasthan) == {"name", "lat", "lon", "cities"}


@pytest.fixture(scope="module")
def big_catalogue(tmp_path_factory):
    folder = tmp_path_factory.mktemp("catalogue")
    generate_catalogue.write(folder, generate_catalogue.build(2026))
    return folder


def test_states_endpoint_on_the_big_catalogue(big_catalogue):
    code = """
import json
from fastapi.testclient import TestClient
from app.main import app

print(json.dumps(TestClient(app).get("/states").json()))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, "CATALOGUE_DIR": str(big_catalogue), "LLM_PROVIDER": "mock"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)

    assert len(body) == 13
    assert sum(len(state["cities"]) for state in body) == 16

    cities = {state["name"]: [c["name"] for c in state["cities"]] for state in body}
    assert cities["Rajasthan"] == ["Jaipur", "Udaipur"]
    assert cities["Uttar Pradesh"] == ["Agra", "Varanasi"]
    assert cities["West Bengal"] == ["Darjeeling", "Kolkata"]

    for state in body:
        for city in state["cities"]:
            assert city["tagline"], city["name"]  # the hover card needs a tagline