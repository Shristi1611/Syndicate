import math
from datetime import date

from app import market, seasons
from app.config import settings
from app.inventory import ACTIVITIES, HOTELS, HUBS, flights_between, list_price
from app.profile import TravellerProfile, missing_fields, or_list

ROOM_CAPACITY = 3          # assumption: one room sleeps up to 3 people
HOTEL_BUDGET_SHARE = 0.55  # a hotel should take at most 55% of what is left after flights
MAX_ACTIVITIES = 3
STOP_PENALTY = 1500        # rupees: a one-stop flight must be this much cheaper to win
SEASON_NOTE_PCT = 8        # mention the season when hotel rates move by at least this much


def _overlap(item: dict, interests: list[str]) -> int:
    return len(set(item.get("tags", [])) & set(interests))


def _line(item: dict, quantity: int, unit: str, price: int | None = None) -> dict:
    price = list_price(item) if price is None else price
    return {
        "item_id": item["id"],
        "name": item["name"],
        "category": item.get("category", "hotel"),
        "unit": unit,
        "unit_price": price,
        "quantity": quantity,
        "total": price * quantity,
    }


def _chosen_hotel(p: TravellerProfile, rooms: int, free_rooms, dated: bool) -> dict:
    """The traveller picked this hotel. Check it is allowed before using it."""
    hotel = HOTELS.get(p.hotel_id)
    if hotel is None:
        raise ValueError(f"Unknown hotel: {p.hotel_id}")
    if hotel["destination"] != p.destination:
        raise ValueError(f"{hotel['name']} is not in {p.destination}")
    if p.stairs_free and not hotel["stairs_free"]:
        raise ValueError(f"{hotel['name']} is not step-free")
    available = free_rooms(hotel)
    if available < rooms:
        where = " free on those dates" if dated else ""
        raise ValueError(f"{hotel['name']} has only {available} room(s){where}")
    return hotel


def _pick_flight(flights: list[dict]) -> dict:
    """Cheapest option, counting a connection as a cost."""
    return min(flights, key=lambda f: (list_price(f) + STOP_PENALTY * f["stops"], f["id"]))


def _flight_line(p: TravellerProfile, notes: list[str], factor: float | None) -> dict | None:
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

    chosen = _pick_flight(routes)
    price = seasons.adjust(list_price(chosen), factor) if factor is not None else list_price(chosen)
    return _line(chosen, p.travellers * 2, "person-trip", price)  # out and back


def plan_trip(profile: dict) -> dict:
    """Pick a hotel, flights, a transfer and a few activities that fit the profile.

    Without a start date everything is priced at the year-round list price. With one,
    hotels and flights follow the season. With the market simulation on, hotels also follow
    demand and are skipped when they are sold out. Tours and transfers stay flat."""
    p = TravellerProfile(**profile)
    missing = missing_fields(p)
    if missing:
        raise ValueError(f"Profile is incomplete, missing: {', '.join(missing)}")

    notes = []
    rooms = math.ceil(p.travellers / ROOM_CAPACITY)

    start = date.fromisoformat(p.start_date) if p.start_date else None
    snap = market.snapshot() if settings.market_enabled and start else None

    def free_rooms(h: dict) -> int:
        return snap.free_rooms(h, start, p.nights) if snap else h["rooms_available"]

    # --- Season (only when the traveller gave a start date) ---
    stay = h_factor = f_factor = None
    if start:
        h_factor = seasons.hotel_factor(p.destination, start, p.nights)
        f_factor = seasons.flight_factor(p.destination, start, p.nights)
        stay = seasons.stay_info(p.destination, start, p.nights)
        change = stay["hotel_change_pct"]
        if abs(change) >= SEASON_NOTE_PCT:
            direction = "above" if change > 0 else "below"
            notes.append(
                f"{stay['season'].capitalize()}: hotel rates for these dates are about "
                f"{abs(change)}% {direction} the year-round rate."
            )

    if snap and snap.demand(p.destination) > 1:
        notes.append(f"Demand for {p.destination} is surging right now, so rooms are scarcer and rates are higher.")
    elif snap and snap.demand(p.destination) < 1:
        notes.append(f"Demand for {p.destination} is soft right now, so rates are lower.")

    def hotel_price(h: dict) -> int:
        base = list_price(h)
        if h_factor is None:
            return base
        factor = h_factor * (snap.price_pressure(h, start, p.nights) if snap else 1.0)
        return seasons.adjust(base, factor)

    # --- Flights (optional: only when the traveller says where they are flying from) ---
    flight = _flight_line(p, notes, f_factor) if p.origin else None
    flights_total = flight["total"] if flight else 0
    if flights_total > p.budget_total:
        notes.append("The flights alone cost more than your budget.")
    hotel_budget = max(0, p.budget_total - flights_total)

    # --- Hotel ---
    sold_out = 0
    if p.hotel_id:
        hotel = _chosen_hotel(p, rooms, free_rooms, dated=snap is not None)
        if hotel_price(hotel) * p.nights * rooms > p.budget_total:
            notes.append(f"{hotel['name']} alone costs more than your budget.")
    else:
        hotels = [h for h in HOTELS.values() if h["destination"] == p.destination]
        if p.stairs_free:
            hotels = [h for h in hotels if h["stairs_free"]]
        if not hotels:
            raise ValueError("No hotel matches these needs")

        if snap:
            open_hotels = [h for h in hotels if free_rooms(h) >= rooms]
            sold_out = len(hotels) - len(open_hotels)
            if not open_hotels:
                raise ValueError("Every matching hotel is sold out on these dates")
            if sold_out:
                notes.append(f"{sold_out} matching hotel(s) sold out on these dates.")
            hotels = open_hotels

        def hotel_cost(h: dict) -> int:
            return hotel_price(h) * p.nights * rooms

        affordable = [h for h in hotels if hotel_cost(h) <= hotel_budget * HOTEL_BUDGET_SHARE]
        if affordable:
            hotel = max(affordable, key=lambda h: (_overlap(h, p.interests), h["star"], -hotel_cost(h)))
        else:
            hotel = min(hotels, key=hotel_cost)
            notes.append("No hotel fits comfortably in the budget; showing the cheapest option.")

    items = [_line(hotel, p.nights * rooms, "room-night", hotel_price(hotel))]
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

    market_info = None
    if snap:
        market_info = {
            "demand": snap.demand(p.destination),
            "hotel_occupancy_pct": round(100 * snap.occupancy(hotel, start, p.nights)),
            "hotel_price_pressure_pct": round((snap.price_pressure(hotel, start, p.nights) - 1) * 100),
            "sold_out_hotels": sold_out,
        }

    return {
        "profile": p.model_dump(),
        "stay": stay,
        "market": market_info,
        "items": items,
        "list_total": spent,
        "budget": p.budget_total,
        "within_budget": spent <= p.budget_total,
        "notes": notes,
    }