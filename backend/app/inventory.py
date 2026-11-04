import json

from app.config import CATALOGUE_DIR

DATA_DIR = CATALOGUE_DIR


def _load(filename: str) -> list[dict]:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


SUPPLIERS = {s["id"]: s for s in _load("suppliers.json")}
HOTELS = {h["id"]: h for h in _load("hotels.json")}
ACTIVITIES = {a["id"]: a for a in _load("activities.json")}


def get_item(item_id: str) -> dict | None:
    """Find a hotel or activity by its id."""
    return HOTELS.get(item_id) or ACTIVITIES.get(item_id)


def get_supplier(supplier_id: str) -> dict | None:
    return SUPPLIERS.get(supplier_id)


def list_price(item: dict) -> int:
    """Public price: per night for hotels, per person for activities."""
    return item.get("list_price_per_night") or item["list_price_per_person"]


def floor_price(item: dict) -> int:
    """HIDDEN lowest price the supplier accepts. Never show this to the traveller agent."""
    supplier = SUPPLIERS[item["supplier_id"]]
    return round(list_price(item) * supplier["floor_ratio"])