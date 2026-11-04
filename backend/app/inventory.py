import json

from app.config import CATALOGUE_DIR

DATA_DIR = CATALOGUE_DIR


def _load(filename: str) -> list[dict]:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def _load_optional(filename: str) -> list[dict]:
    """Some catalogues (like the small test one) have no flights."""
    return _load(filename) if (DATA_DIR / filename).exists() else []


SUPPLIERS = {s["id"]: s for s in _load("suppliers.json")}
HOTELS = {h["id"]: h for h in _load("hotels.json")}
ACTIVITIES = {a["id"]: a for a in _load("activities.json")}
FLIGHTS = {f["id"]: f for f in _load_optional("flights.json")}


def _destinations() -> dict[str, dict]:
    """The cities a traveller can choose. Older catalogues without destinations.json
    fall back to the cities their hotels are in."""
    path = DATA_DIR / "destinations.json"
    if path.exists():
        return {d["name"]: d for d in json.loads(path.read_text(encoding="utf-8"))}
    return {name: {"name": name} for name in sorted({h["destination"] for h in HOTELS.values()})}


DESTINATIONS = _destinations()

# Cities flights leave from.
HUBS = sorted(name for name, d in DESTINATIONS.items() if d.get("hub"))


def get_item(item_id: str) -> dict | None:
    """Find a hotel, activity or flight by its id."""
    return HOTELS.get(item_id) or ACTIVITIES.get(item_id) or FLIGHTS.get(item_id)


def get_supplier(supplier_id: str) -> dict | None:
    return SUPPLIERS.get(supplier_id)


def flights_between(origin: str, destination: str) -> list[dict]:
    return [f for f in FLIGHTS.values() if f["origin"] == origin and f["destination"] == destination]


def list_price(item: dict) -> int:
    """Public price: per night for hotels, per person for activities and flights."""
    return item.get("list_price_per_night") or item["list_price_per_person"]


def floor_price(item: dict) -> int:
    """HIDDEN lowest price the supplier accepts. Never show this to the traveller agent."""
    supplier = SUPPLIERS[item["supplier_id"]]
    return round(list_price(item) * supplier["floor_ratio"])