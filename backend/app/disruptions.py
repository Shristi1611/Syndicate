import json
import sqlite3
import time
import uuid
from contextlib import closing

from app.bookings import _booked_rooms, _connect
from app.inventory import HOTELS, get_item, list_price
from app.negotiation import negotiate

RAIN_TAGS = {"beachfront", "water", "adventure"}  # activities that heavy rain ruins
MAX_ALTERNATIVES = 2

EVENT_TEXT = {
    "hotel_overbooked": "Your hotel has overbooked and cannot honour your reservation.",
    "heavy_rain": "Heavy rain is forecast and will affect outdoor plans.",
    "flight_cancelled": "Your flight was cancelled, so your arrival is delayed.",
}


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            booking_id TEXT NOT NULL,
            event TEXT NOT NULL,
            options TEXT NOT NULL,
            status TEXT NOT NULL,
            created REAL NOT NULL
        )
        """
    )


def _load(conn: sqlite3.Connection, booking_id: str) -> dict:
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise LookupError(f"Unknown booking: {booking_id}")
    if row["status"] != "confirmed":
        raise ValueError("Only a confirmed booking can be changed")
    return json.loads(row["trip"])


def _option(option_id: str, label: str, cost_delta: int, **extra) -> dict:
    """cost_delta > 0 means the traveller pays more, < 0 means money comes back."""
    return {"option_id": option_id, "label": label, "cost_delta": cost_delta, **extra}


def _best_price(item_id: str) -> int:
    """Negotiate a new item. We never pay above its list price."""
    result = negotiate(item_id, [], list_price(get_item(item_id)))
    return result["deal"]["price"] if result["deal"] else list_price(get_item(item_id))


def _lines(trip: dict, category: str) -> list[dict]:
    return [line for line in trip["items"] if line["category"] == category]


def _hotel_overbooked(conn: sqlite3.Connection, trip: dict):
    profile = trip["profile"]
    hotel = _lines(trip, "hotel")[0]
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
    candidates.sort(key=lambda h: abs(list_price(h) - hotel["unit_price"]))

    options = []
    for alt in candidates[:MAX_ALTERNATIVES]:
        unit = _best_price(alt["id"])
        delta = unit * hotel["quantity"] - hotel["final_total"]
        options.append(
            _option(
                f"move:{alt['id']}",
                f"Move to {alt['name']} ({alt['star']} star)",
                delta,
                new_unit_price=unit,
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
    affected = [
        line
        for line in trip["items"]
        if line["category"] not in ("hotel", "transfer")
        and (line["category"] == "adventure" or RAIN_TAGS & set(get_item(line["item_id"]).get("tags", [])))
    ]
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


def _flight_cancelled(conn: sqlite3.Connection, trip: dict):
    transfers = _lines(trip, "transfer")
    if not transfers:
        raise ValueError("This trip has no airport transfers to change")

    hotel = _lines(trip, "hotel")[0]
    rooms = hotel["quantity"] // trip["profile"]["nights"]
    unit = _best_price(hotel["item_id"])

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
        trip = _load(conn, booking_id)
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