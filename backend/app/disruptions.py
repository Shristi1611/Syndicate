import json
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date

from app import seasons
from app.bookings import _booked_rooms, _connect
from app.guard import check_offer
from app.inventory import FLIGHTS, HOTELS, flights_between, get_item, list_price
from app.negotiation import negotiate

RAIN_TAGS = {"beachfront", "water", "adventure"}  # activities that heavy rain ruins
MAX_ALTERNATIVES = 2
PROPOSAL_TTL_SECONDS = 15 * 60  # options must be approved within 15 minutes

EVENT_TEXT = {
    "hotel_overbooked": "Your hotel has overbooked and cannot honour your reservation.",
    "heavy_rain": "Heavy rain is forecast and will affect outdoor plans.",
    "flight_cancelled": "Your flight was cancelled, so your arrival is delayed.",
}

NO_LONGER_APPLIES = "This option no longer applies to your booking"


def _ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            booking_id TEXT NOT NULL,
            event TEXT NOT NULL,
            options TEXT NOT NULL,
            status TEXT NOT NULL,
            created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applied_changes (
            proposal_id TEXT PRIMARY KEY,
            option_id TEXT NOT NULL,
            result TEXT NOT NULL,
            created REAL NOT NULL
        );
        """
    )


def _load_booking(conn: sqlite3.Connection, booking_id: str):
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise LookupError(f"Unknown booking: {booking_id}")
    if row["status"] != "confirmed":
        raise ValueError("Only a confirmed booking can be changed")
    return row, json.loads(row["trip"])


def _option(option_id: str, label: str, cost_delta: int, **extra) -> dict:
    """cost_delta > 0 means the traveller pays more, < 0 means money comes back."""
    return {"option_id": option_id, "label": label, "cost_delta": cost_delta, **extra}


# ---------------------------------------------------------- prices for the dates


def _start(trip: dict) -> date | None:
    value = trip["profile"].get("start_date")  # bookings made before dates existed have none
    return date.fromisoformat(value) if value else None


def _hotel_listed(trip: dict, hotel: dict) -> int:
    """The list price for this trip's dates. Without dates it is the year-round price."""
    base = list_price(hotel)
    start = _start(trip)
    if start is None:
        return base
    return seasons.adjust(base, seasons.hotel_factor(hotel["destination"], start, trip["profile"]["nights"]))


def _flight_listed(trip: dict, flight: dict) -> int:
    base = list_price(flight)
    start = _start(trip)
    if start is None:
        return base
    return seasons.adjust(base, seasons.flight_factor(flight["destination"], start, trip["profile"]["nights"]))


def _best_price(item_id: str, listed: int) -> int:
    """Negotiate a new item against the list price for the traveller's dates.
    We never pay above that list price."""
    result = negotiate(item_id, [], listed, list_override=listed)
    return result["deal"]["price"] if result["deal"] else listed


def _guard(item_id: str, price: int, listed: int) -> None:
    """The same Rules Guard that checks every supplier offer checks every new price."""
    result = check_offer(item_id, {"price": price, "perks": []}, 1, list_override=listed)
    if not result.ok:
        raise ValueError("; ".join(result.violations))


# ------------------------------------------------------------------ trip helpers


def _lines(trip: dict, category: str) -> list[dict]:
    return [line for line in trip["items"] if line["category"] == category]


def _hotel_line(trip: dict, movable: bool = False) -> dict:
    hotels = _lines(trip, "hotel")
    if not hotels:
        raise ValueError("This trip has no hotel to change")
    if movable and _lines(trip, "hotel_extra"):
        raise ValueError(
            "Extra nights were added to this stay, so it can no longer be changed "
            "automatically. A human agent needs to handle it."
        )
    return hotels[0]


def _rain_affected(trip: dict) -> list[dict]:
    return [
        line
        for line in trip["items"]
        if line["category"] not in ("hotel", "hotel_extra", "transfer", "flight")
        and (line["category"] == "adventure" or RAIN_TAGS & set(get_item(line["item_id"]).get("tags", [])))
    ]


def _flight_text(flight: dict) -> str:
    stops = "non-stop" if flight["stops"] == 0 else "1 stop"
    hours, minutes = divmod(flight["duration_minutes"], 60)
    return f"{flight['airline']}, {stops}, {hours}h {minutes:02d}m"


# ---------------------------------------------------------------- proposing


def _hotel_overbooked(conn: sqlite3.Connection, trip: dict):
    profile = trip["profile"]
    hotel = _hotel_line(trip, movable=True)
    rooms = hotel["quantity"] // profile["nights"]
    current = get_item(hotel["item_id"])

    candidates = [
        h
        for h in HOTELS.values()
        if h["destination"] == current["destination"]
        and h["id"] != hotel["item_id"]
        and (h["stairs_free"] or not profile["stairs_free"])
        and h["rooms_available"] - _booked_rooms(conn, h["id"]) >= rooms
    ]
    candidates.sort(key=lambda h: abs(_hotel_listed(trip, h) - hotel["unit_price"]))

    options = []
    for alt in candidates[:MAX_ALTERNATIVES]:
        listed = _hotel_listed(trip, alt)
        unit = _best_price(alt["id"], listed)
        delta = unit * hotel["quantity"] - hotel["final_total"]
        options.append(
            _option(
                f"move:{alt['id']}",
                f"Move to {alt['name']} ({alt['star']} star)",
                delta,
                new_unit_price=unit,
                list_price=listed,
                details=f"{rooms} room(s) for {profile['nights']} nights at {unit} rupees per night, negotiated",
            )
        )

    options.append(
        _option(
            "cancel_hotel",
            "Cancel the hotel with a full refund",
            -hotel["final_total"],
            details="No cancellation fee, because the supplier is at fault. You would need to find your own stay.",
        )
    )
    return [hotel["name"]], options


def _heavy_rain(conn: sqlite3.Connection, trip: dict):
    affected = _rain_affected(trip)
    if not affected:
        raise ValueError("Nothing in this trip is affected by heavy rain")

    names = [line["name"] for line in affected]
    refund = sum(line["final_total"] for line in affected)
    return names, [
        _option("keep_all", "Keep everything as planned", 0, details="You risk getting rained out."),
        _option(
            "cancel_affected",
            f"Cancel {', '.join(names)} with a full refund",
            -refund,
            details="Weather cancellations carry no fee.",
        ),
    ]


def _flight_cancelled_with_flights(trip: dict, line: dict):
    """The trip includes flights: offer other flights on the same route, or a refund."""
    current = get_item(line["item_id"])
    alternatives = [
        f
        for f in flights_between(current["origin"], current["destination"])
        if f["id"] != line["item_id"]
    ]
    alternatives.sort(key=lambda f: (_flight_listed(trip, f), f["id"]))

    options = []
    for alt in alternatives[:MAX_ALTERNATIVES]:
        listed = _flight_listed(trip, alt)
        unit = _best_price(alt["id"], listed)
        options.append(
            _option(
                f"rebook:{alt['id']}",
                f"Rebook on {alt['airline']}",
                unit * line["quantity"] - line["final_total"],
                new_unit_price=unit,
                list_price=listed,
                details=(
                    f"{_flight_text(alt)}, both directions, {unit} rupees per person-trip, negotiated. "
                    "Your airport pickup moves to the new arrival time at no charge."
                ),
            )
        )

    options.append(
        _option(
            "cancel_flight",
            "Cancel the flights with a full refund",
            -line["final_total"],
            details="No cancellation fee, because the airline is at fault. You would arrange your own travel.",
        )
    )
    return [line["name"]], options


def _flight_cancelled(conn: sqlite3.Connection, trip: dict):
    flights = _lines(trip, "flight")
    if flights:
        return _flight_cancelled_with_flights(trip, flights[0])

    transfers = _lines(trip, "transfer")
    if not transfers:
        raise ValueError("This trip has no airport transfers to change")

    hotel = _hotel_line(trip)
    rooms = hotel["quantity"] // trip["profile"]["nights"]
    listed = hotel["unit_price"]  # an extra night costs what the booked stay costs per night
    unit = _best_price(hotel["item_id"], listed)

    return [line["name"] for line in transfers], [
        _option(
            "reschedule",
            "Reschedule the airport pickup",
            0,
            details="We rebook your pickup for the new arrival time. Your first hotel night may be lost.",
        ),
        _option(
            "reschedule_extra_night",
            "Reschedule the pickup and add one extra hotel night",
            unit * rooms,
            new_unit_price=unit,
            list_price=listed,
            details=f"{rooms} room(s) at {unit} rupees for the night, negotiated, so you do not lose a night.",
        ),
        _option(
            "cancel_transfers",
            "Cancel the airport transfers with a full refund",
            -sum(line["final_total"] for line in transfers),
            details="Disruption cancellations carry no fee. You would arrange your own transport.",
        ),
    ]


BUILDERS = {
    "hotel_overbooked": _hotel_overbooked,
    "heavy_rain": _heavy_rain,
    "flight_cancelled": _flight_cancelled,
}


def propose(booking_id: str, event: str) -> dict:
    """Work out the options for a disruption. Changes nothing until the traveller approves one."""
    if event not in BUILDERS:
        raise ValueError(f"Unknown event: {event}")

    with closing(_connect()) as conn:
        _ensure(conn)
        _, trip = _load_booking(conn, booking_id)
        affected, options = BUILDERS[event](conn, trip)

        proposal_id = "P-" + uuid.uuid4().hex[:8].upper()
        conn.execute(
            "INSERT INTO proposals (id, booking_id, event, options, status, created) "
            "VALUES (?, ?, ?, ?, 'open', ?)",
            (proposal_id, booking_id, event, json.dumps(options), time.time()),
        )
        conn.commit()

    return {
        "proposal_id": proposal_id,
        "booking_id": booking_id,
        "event": event,
        "message": EVENT_TEXT[event],
        "affected": affected,
        "options": options,
        "requires_confirmation": True,
    }


# ----------------------------------------------------------------- applying


def _change(conn: sqlite3.Connection, booking_id: str, trip: dict, option_id: str, option: dict) -> None:
    """Apply one option to the trip and to the room stock. Raises if it no longer applies."""
    items = trip["items"]
    nights = trip["profile"]["nights"]

    if option_id in ("keep_all", "reschedule"):
        return  # nothing to change in the booking itself

    if option_id == "cancel_affected":
        ids = {line["item_id"] for line in _rain_affected(trip)}
        if not ids:
            raise ValueError(NO_LONGER_APPLIES)
        trip["items"] = [line for line in items if line["item_id"] not in ids]
        return

    if option_id == "cancel_transfers":
        if not _lines(trip, "transfer"):
            raise ValueError(NO_LONGER_APPLIES)
        trip["items"] = [line for line in items if line["category"] != "transfer"]
        return

    if option_id == "cancel_flight":
        if not _lines(trip, "flight"):
            raise ValueError(NO_LONGER_APPLIES)
        trip["items"] = [line for line in items if line["category"] != "flight"]
        return

    if option_id.startswith("rebook:"):
        flights = _lines(trip, "flight")
        if not flights:
            raise ValueError(NO_LONGER_APPLIES)
        old = flights[0]
        current = get_item(old["item_id"])
        new_id = option_id.split(":", 1)[1]
        new = FLIGHTS.get(new_id)
        same_route = new is not None and (new["origin"], new["destination"]) == (
            current["origin"],
            current["destination"],
        )
        if not same_route or new_id == old["item_id"]:
            raise ValueError(NO_LONGER_APPLIES)

        unit = option["new_unit_price"]
        listed = _flight_listed(trip, new)
        _guard(new_id, unit, listed)
        new_line = {
            "item_id": new_id,
            "name": new["name"],
            "category": "flight",
            "unit": old["unit"],
            "unit_price": listed,
            "quantity": old["quantity"],
            "total": listed * old["quantity"],
            "final_unit_price": unit,
            "final_total": unit * old["quantity"],
            "perks": [],
        }
        trip["items"] = [new_line if line is old else line for line in items]
        return

    if option_id == "cancel_hotel":
        hotel = _hotel_line(trip, movable=True)
        trip["items"] = [line for line in items if line is not hotel]
        conn.execute(
            "UPDATE booking_items SET status = 'cancelled' WHERE booking_id = ? AND item_id = ?",
            (booking_id, hotel["item_id"]),
        )
        return

    if option_id == "reschedule_extra_night":
        hotel = _hotel_line(trip)
        rooms = hotel["quantity"] // nights
        unit = option["new_unit_price"]
        listed = hotel["unit_price"]
        _guard(hotel["item_id"], unit, listed)
        items.append(
            {
                "item_id": hotel["item_id"],
                "name": f"Extra night: {hotel['name']}",
                "category": "hotel_extra",
                "unit": hotel["unit"],
                "unit_price": listed,
                "quantity": rooms,
                "total": listed * rooms,
                "final_unit_price": unit,
                "final_total": unit * rooms,
                "perks": [],
            }
        )
        return

    if option_id.startswith("move:"):
        new_id = option_id.split(":", 1)[1]
        new = HOTELS.get(new_id)
        if new is None:
            raise ValueError(NO_LONGER_APPLIES)

        hotel = _hotel_line(trip, movable=True)
        rooms = hotel["quantity"] // nights
        if trip["profile"]["stairs_free"] and not new["stairs_free"]:
            raise ValueError(f"{new['name']} is not step-free")
        if new["rooms_available"] - _booked_rooms(conn, new_id) < rooms:
            raise ValueError(f"{new['name']} no longer has enough rooms")

        unit = option["new_unit_price"]
        listed = _hotel_listed(trip, new)
        _guard(new_id, unit, listed)
        new_line = {
            "item_id": new_id,
            "name": new["name"],
            "category": "hotel",
            "unit": hotel["unit"],
            "unit_price": listed,
            "quantity": hotel["quantity"],
            "total": listed * hotel["quantity"],
            "final_unit_price": unit,
            "final_total": unit * hotel["quantity"],
            "perks": [],
        }
        trip["items"] = [new_line if line is hotel else line for line in items]

        conn.execute(
            "UPDATE booking_items SET status = 'cancelled' WHERE booking_id = ? AND item_id = ?",
            (booking_id, hotel["item_id"]),
        )
        conn.execute(
            "INSERT INTO booking_items (booking_id, item_id, rooms, status) VALUES (?, ?, ?, 'confirmed')",
            (booking_id, new_id, rooms),
        )
        return

    raise ValueError(f"Unknown option: {option_id}")


def apply_option(booking_id: str, proposal_id: str, option_id: str) -> dict:
    """The traveller's approval: apply one option. Applying the same option twice is safe."""
    with closing(_connect()) as conn:
        _ensure(conn)
        conn.execute("BEGIN IMMEDIATE")  # lock so two requests cannot change the booking at once

        proposal = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if proposal is None or proposal["booking_id"] != booking_id:
            raise LookupError(f"Unknown proposal: {proposal_id}")

        done = conn.execute(
            "SELECT * FROM applied_changes WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if done is not None:
            if done["option_id"] != option_id:
                raise ValueError("This disruption was already resolved with a different option")
            return {**json.loads(done["result"]), "already_applied": True}

        if time.time() - proposal["created"] > PROPOSAL_TTL_SECONDS:
            raise ValueError("These options have expired. Please check the disruption again.")

        options = {o["option_id"]: o for o in json.loads(proposal["options"])}
        if option_id not in options:
            raise ValueError(f"Unknown option: {option_id}")

        row, trip = _load_booking(conn, booking_id)
        old_total = row["total"]
        _change(conn, booking_id, trip, option_id, options[option_id])
        new_total = sum(line["final_total"] for line in trip["items"])

        conn.execute(
            "UPDATE bookings SET trip = ?, total = ? WHERE id = ?",
            (json.dumps(trip), new_total, booking_id),
        )
        result = {
            "booking_id": booking_id,
            "proposal_id": proposal_id,
            "event": proposal["event"],
            "option_id": option_id,
            "label": options[option_id]["label"],
            "old_total": old_total,
            "new_total": new_total,
            "cost_delta": new_total - old_total,
            "within_budget": new_total <= trip["profile"]["budget_total"],
        }
        conn.execute(
            "INSERT INTO applied_changes (proposal_id, option_id, result, created) VALUES (?, ?, ?, ?)",
            (proposal_id, option_id, json.dumps(result), time.time()),
        )
        conn.commit()

    return {**result, "already_applied": False}