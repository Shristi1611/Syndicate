import json
from pathlib import Path

from app.states import STATES

MAP = Path(__file__).resolve().parents[2] / "frontend" / "public" / "data" / "india.json"


def features():
    return json.loads(MAP.read_text(encoding="utf-8"))["features"]


def points(coords):
    """Every [lon, lat] pair inside a GeoJSON coordinate tree."""
    if coords and isinstance(coords[0][0], (int, float)):
        yield from coords
    else:
        for part in coords:
            yield from points(part)


def test_map_has_the_expected_layers():
    kinds = [f["properties"]["kind"] for f in features()]
    assert kinds.count("outline") == 1
    assert kinds.count("state") == 36
    assert kinds.count("extra") == 2


def test_every_destination_state_is_on_the_map():
    flagged = {f["properties"]["ours"] for f in features() if f["properties"].get("ours")}
    assert flagged == set(STATES)  # a new destination state without a shape fails here


def test_map_stays_inside_india_and_stays_small():
    for feature in features():
        for lon, lat in points(feature["geometry"]["coordinates"]):
            assert 67 <= lon <= 98 and 6 <= lat <= 38
    assert MAP.stat().st_size < 400 * 1024
