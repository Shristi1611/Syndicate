"""Build the small India map file that the website draws.

Run from the backend folder:

    pip install shapely
    python build_india_map.py

Data: Natural Earth (public domain), downloaded once into a cache folder.
  - the outline comes from Natural Earth's India point-of-view country file
  - the 36 states and union territories come from its standard admin-1 file
Two regions are inside India's own outline but covered by no state polygon. They are written as a
separate "extra" layer, attached to no state, so that choice stays easy to change.
"""
import argparse
import json
import urllib.request
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from app.states import STATES  # our 13 states that have destinations

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
OUTLINE_FILE = "ne_10m_admin_0_countries_ind.geojson"
STATES_FILE = "ne_10m_admin_1_states_provinces.geojson"

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "data" / "india.json"
DEFAULT_CACHE = Path(__file__).resolve().parent / ".map_cache"

TOLERANCE = 0.012   # degrees, about 1 km: plenty for a hero map, and keeps the file small
DIGITS = 3
MIN_AREA = 0.0006   # drop specks smaller than this (square degrees), keep real islands
EXTRA_MIN_AREA = 0.05
ALIASES = {"Andaman and Nicobar": "Andaman and Nicobar Islands"}  # Natural Earth's spelling -> ours


def fetch(name: str, cache: Path) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    if not path.exists():
        print("downloading", name)
        urllib.request.urlretrieve(f"{BASE}/{name}", path)
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(value):
    if isinstance(value, float):
        return round(value, DIGITS)
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    return value


def tidy(geom):
    """Simplify, then drop tiny specks. A state made only of tiny islands keeps all of them."""
    geom = geom.simplify(TOLERANCE, preserve_topology=True)
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    parts = [p for p in parts if p.geom_type == "Polygon"]
    big = [p for p in parts if p.area >= MIN_AREA]
    kept = big or parts
    return kept[0] if len(kept) == 1 else unary_union(kept)


def feature(kind: str, geom, **props) -> dict:
    g = mapping(geom)
    return {
        "type": "Feature",
        "properties": {"kind": kind, **props},
        "geometry": {"type": g["type"], "coordinates": rounded(g["coordinates"])},
    }


def build(cache: Path) -> dict:
    outline_data = fetch(OUTLINE_FILE, cache)
    states_data = fetch(STATES_FILE, cache)

    india = next(f for f in outline_data["features"] if f["properties"]["ADM0_A3"] == "IND")
    outline = shape(india["geometry"])

    raw_states = {
        f["properties"]["name"]: shape(f["geometry"])
        for f in states_data["features"]
        if f["properties"].get("adm0_a3") == "IND"
    }
    covered = unary_union(list(raw_states.values()))

    features = [feature("outline", tidy(outline), name="India")]

    for name, geom in sorted(raw_states.items()):
        ours = ALIASES.get(name, name)
        features.append(feature("state", tidy(geom), name=name, ours=ours if ours in STATES else None))

    extra = outline.difference(covered.buffer(0.02))
    pieces = list(extra.geoms) if extra.geom_type == "MultiPolygon" else [extra]
    for i, piece in enumerate(sorted((p for p in pieces if p.area >= EXTRA_MIN_AREA), key=lambda p: -p.area), 1):
        features.append(feature("extra", tidy(piece), name=f"Region {i} (inside India's outline, no state attached)"))

    found = {f["properties"]["ours"] for f in features if f["properties"].get("ours")}
    missing = set(STATES) - found
    assert not missing, f"These destination states were not found in the map data: {missing}"

    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the India map file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    data = build(args.cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    kinds = [f["properties"]["kind"] for f in data["features"]]
    print(
        f"Wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB): "
        f"{kinds.count('state')} states, {kinds.count('extra')} extra regions, 1 outline"
    )


if __name__ == "__main__":
    main()
