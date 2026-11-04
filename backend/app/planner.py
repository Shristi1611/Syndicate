import math

from app.inventory import ACTIVITIES, HOTELS, HUBS, flights_between, list_price
from app.profile import TravellerProfile, missing_fields, or_list

ROOM_CAPACITY = 3          # assumption: one room sleeps up to 3 people
HOTEL_BUDGET_SHARE = 0.55  # a hotel should take at most 55% of what is left after flights
MAX_ACTIVITIES = 3
STOP_PENALTY = 1500        # rupees: a one-stop flight must be this much cheaper to win


def _overlap(item: dict, interests: list[str]) -> int:
    return len(set(item.get("tags", [])) & set(interests))


def _line(item: dict, quantity: int, unit: str) -> dict:
    price = list_price(item)
    return {
        "item_id": item["id"],
        "name": item["name"],
        "category": item.get("category", "hotel"),
        "unit": unit,
        "unit_price": price,
        "quantity": quantity,
        "total": price * quantity,
    }


def _chosen_hotel(p: TravellerProfile, rooms: int) -> dict:
    """The traveller picked this hotel. Check it is allowed before using it."""
    hotel = HOTELS.get(p.hotel_id)
    if hotel is None:
        raise ValueError(f"Unknown hotel: {p.hotel_id}")
    if hotel["destination"] != p.destination:
        raise ValueError(f"{hotel['name']} is not in {p.destination}")
    if p.stairs_free and not hotel["stairs_free"]:
        raise ValueError(f"{hotel['name']} is not step-free")
    if hotel["rooms_available"] < rooms:
        raise ValueError(f"{hotel['name']} has only {hotel['rooms_available']} room(s)")
    return hotel


def _pick_flight(flights: list[dict]) -> dict:
    """Cheapest option, counting a connection as a cost."""
    return min(flights, key=lambda f: (list_price(f) + STOP_PENALTY * f["stops"], f["id"]))


def _flight_line(p: TravellerProfile, notes: list[str]) -> dict | None:
    """Round-trip flights from the traveller's starting city, or None with a note."""
    if p.origin == p.destination:
        raise ValueError("Your starting city and destination are the same.")
    if p.origin not in HUBS:
        if not HUBS:
            raise ValueError("Flights are not available in this catalogue.")
        raise ValueError(f"I can include flights from {or_list(HUBS)}, not {p.origin}.")

    routes = flights_between(p.origin, p.destination)
    if not routes:
        notes.append(
            f"There are no flights from {p.origin} to {p.destination}; plan to travel by road or rail."
        )
        return None
    return _line(_pick_flight(routes), p.travellers * 2, "person-trip")  # out and back


def plan_trip(profile: dict) -> dict:
    """Pick a hotel, flights, a transfer and a few activities that fit the profile. List prices only."""
    p = TravellerProfile(**profile)
    missing = missing_fields(p)
    if missing:
        raise ValueError(f"Profile is incomplete, missing: {', '.join(missing)}")

    notes = []
    rooms = math.ceil(p.travellers / ROOM_CAPACITY)

    # --- Flights (optional: only when the traveller says where they are flying from) ---
    flight = _flight_line(p, notes) if p.origin else None
    flights_total = flight["total"] if flight else 0
    if flights_total > p.budget_total:
        notes.append("The flights alone cost more than your budget.")
    hotel_budget = max(0, p.budget_total - flights_total)

    # --- Hotel ---
    if p.hotel_id:
        hotel = _chosen_hotel(p, rooms)
        if list_price(hotel) * p.nights * rooms > p.budget_total:
            notes.append(f"{hotel['name']} alone costs more than your budget.")
    else:
        hotels = [h for h in HOTELS.values() if h["destination"] == p.destination]
        if p.stairs_free:
            hotels = [h for h in hotels if h["stairs_free"]]
        if not hotels:
            raise ValueError("No hotel matches these needs")

        def hotel_cost(h):
            return list_price(h) * p.nights * rooms

        affordable = [h for h in hotels if hotel_cost(h) <= hotel_budget * HOTEL_BUDGET_SHARE]
        if affordable:
            hotel = max(affordable, key=lambda h: (_overlap(h, p.interests), h["star"], -hotel_cost(h)))
        else:
            hotel = min(hotels, key=hotel_cost)
            notes.append("No hotel fits comfortably in the budget; showing the cheapest option.")

    items = [_line(hotel, p.nights * rooms, "room-night")]
    spent = items[0]["total"]

    if flight:
        items.append(flight)
        spent += flight["total"]

    # --- Airport transfer (arrival + departure, per person) ---
    transfers = [a for a in ACTIVITIES.values()
                 if a["destination"] == p.destination and a["category"] == "transfer"]
    if transfers:
        line = _line(transfers[0], p.travellers * 2, "person-trip")
        items.append(line)
        spent += line["total"]

    # --- Activities ---
    acts = [a for a in ACTIVITIES.values()
            if a["destination"] == p.destination and a["category"] != "transfer"]
    if p.stairs_free:
        acts = [a for a in acts if a["stairs_free"]]
    acts.sort(key=lambda a: (-_overlap(a, p.interests), list_price(a)))

    chosen = 0
    for act in acts:
        if chosen == MAX_ACTIVITIES:
            break
        line = _line(act, p.travellers, "person")
        if spent + line["total"] <= p.budget_total:
            items.append(line)
            spent += line["total"]
            chosen += 1

    return {
        "profile": p.model_dump(),
        "items": items,
        "list_total": spent,
        "budget": p.budget_total,
        "within_budget": spent <= p.budget_total,
        "notes": notes,
    }