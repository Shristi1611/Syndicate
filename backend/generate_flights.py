"""Generate flights between the hub cities and every other destination.

Run from the backend folder, AFTER generate_catalogue.py:

    python generate_catalogue.py
    python generate_flights.py

It adds four fictional airlines to suppliers.json and writes flights.json.
Everything is synthetic and comes from a fixed seed, so every run gives the same data.
"""
import argparse
import json
import math
import random
from pathlib import Path

DEFAULT_SEED = 2026
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data"
MIN_FLIGHT_KM = 350  # shorter trips are done by road or rail
REMOTE = {"Leh", "Andaman", "Meghalaya"}  # remote places cost more to fly to

AIRLINE_SUPPLIERS = [
    {
        "id": "S_19", "name": "Crest Air",
        "personality": "no-frills low-fare airline that guards its headline fare and sells add-ons instead",
        "floor_ratio": 0.88, "tradeable": ["extra_baggage"],
        "patience_rounds": 2, "free_cancellation_days": 2,
    },
    {
        "id": "S_20", "name": "Meridian Airways",
        "personality": "full-service carrier, formal, rarely discounts but will include comforts",
        "floor_ratio": 0.90, "tradeable": ["extra_baggage", "free_meal", "seat_selection"],
        "patience_rounds": 2, "free_cancellation_days": 3,
    },
    {
        "id": "S_21", "name": "SkyBridge",
        "personality": "regional airline that likes to fill seats and offers small perks for early bookings",
        "floor_ratio": 0.84, "tradeable": ["extra_baggage", "priority_boarding"],
        "patience_rounds": 3, "free_cancellation_days": 2,
    },
    {
        "id": "S_22", "name": "Indus Wings",
        "personality": "flexible mid-market airline, friendly and open to bundling comforts",
        "floor_ratio": 0.80, "tradeable": ["free_meal", "seat_selection"],
        "patience_rounds": 3, "free_cancellation_days": 4,
    },
]
AIRLINE_IDS = {s["id"] for s in AIRLINE_SUPPLIERS}

# Fare level compared with the cheapest airline.
FARE_LEVEL = {"S_19": 1.00, "S_20": 1.38, "S_21": 1.15, "S_22": 1.25}
OPTIONAL_CARRIERS = ["S_21", "S_22"]


def _km(a: dict, b: dict) -> float:
    """Great-circle distance between two destinations, in kilometres."""
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def build_flights(destinations: list[dict], seed: int = DEFAULT_SEED) -> list[dict]:
    """Flights from every hub city to every other destination. Same seed, same result."""
    rng = random.Random(seed + 101)  # separate from the catalogue's own random stream
    airlines = {s["id"]: s for s in AIRLINE_SUPPLIERS}
    flights = []

    for origin in destinations:
        if not origin.get("hub"):
            continue
        for dest in destinations:
            if dest["name"] == origin["name"]:
                continue
            km = _km(origin, dest)
            if km < MIN_FLIGHT_KM:
                continue

            carriers = ["S_19", "S_20"]
            if rng.random() < 0.6:
                carriers.append(rng.choice(OPTIONAL_CARRIERS))

            for number, sid in enumerate(carriers, start=1):
                stops = 0
                if km > 2400:
                    stops = 1
                elif km > 1200 and sid == "S_19" and rng.random() < 0.45:
                    stops = 1

                fare = 1900 + 2.1 * km
                if dest["name"] in REMOTE:
                    fare *= 1.15
                fare *= FARE_LEVEL[sid] * rng.uniform(0.94, 1.08)
                if stops:
                    fare *= 0.92  # connecting flights are a little cheaper

                minutes = km / 760 * 60 + 50 + stops * 75
                flights.append(
                    {
                        "id": f"F_{origin['code']}_{dest['code']}_{number}",
                        "name": f"{origin['name']} to {dest['name']}, {airlines[sid]['name']}",
                        "category": "flight",
                        "origin": origin["name"],
                        "destination": dest["name"],
                        "airline": airlines[sid]["name"],
                        "stops": stops,
                        "duration_minutes": int(round(minutes / 5) * 5),
                        "tags": [],
                        "stairs_free": True,
                        "list_price_per_person": max(1500, int(round(fare / 50) * 50)),
                        "supplier_id": sid,
                    }
                )
    return flights


def add_to_catalogue(folder: Path, seed: int = DEFAULT_SEED) -> int:
    """Add the airlines to suppliers.json and write flights.json. Safe to run again."""
    destinations = json.loads((folder / "destinations.json").read_text(encoding="utf-8"))
    suppliers = json.loads((folder / "suppliers.json").read_text(encoding="utf-8"))

    suppliers = [s for s in suppliers if s["id"] not in AIRLINE_IDS] + AIRLINE_SUPPLIERS
    flights = build_flights(destinations, seed)

    (folder / "suppliers.json").write_text(
        json.dumps(suppliers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (folder / "flights.json").write_text(
        json.dumps(flights, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(flights)


def main() -> None:
    parser = argparse.ArgumentParser(description="Add flights to the synthetic catalogue.")
    parser.add_argument("--out", type=Path, default=DEFAULT_DIR, help="catalogue folder (default: data)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default 2026)")
    args = parser.parse_args()

    count = add_to_catalogue(args.out, args.seed)
    print(f"Added {len(AIRLINE_SUPPLIERS)} airlines and {count} flights to {args.out}")


if __name__ == "__main__":
    main()