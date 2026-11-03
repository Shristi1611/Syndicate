import math

from app.inventory import ACTIVITIES, HOTELS, list_price
from app.profile import TravellerProfile, missing_fields

ROOM_CAPACITY = 3          # assumption: one room sleeps up to 3 people
HOTEL_BUDGET_SHARE = 0.55  # a hotel should take at most 55% of the total budget
MAX_ACTIVITIES = 3


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


def plan_trip(profile: dict) -> dict:
    """Pick a hotel, a transfer and a few activities that fit the profile. List prices only."""
    p = TravellerProfile(**profile)
    missing = missing_fields(p)
    if missing:
        raise ValueError(f"Profile is incomplete, missing: {', '.join(missing)}")

    notes = []
    rooms = math.ceil(p.travellers / ROOM_CAPACITY)

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

        affordable = [h for h in hotels if hotel_cost(h) <= p.budget_total * HOTEL_BUDGET_SHARE]
        if affordable:
            hotel = max(affordable, key=lambda h: (_overlap(h, p.interests), h["star"], -hotel_cost(h)))
        else:
            hotel = min(hotels, key=hotel_cost)
            notes.append("No hotel fits comfortably in the budget; showing the cheapest option.")

    items = [_line(hotel, p.nights * rooms, "room-night")]
    spent = items[0]["total"]

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