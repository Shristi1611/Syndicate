import json
import sqlite3
import time
import uuid
from contextlib import closing

from app.config import ROOT_DIR
from app.guard import check_offer
from app.inventory import get_item
from app.planner import plan_trip

DB_PATH = ROOT_DIR / "data" / "syndicate.db"
QUOTE_TTL_SECONDS = 15 * 60  # a quote must be confirmed within 15 minutes


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with closing(_connect()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                id TEXT PRIMARY KEY,
                trip TEXT NOT NULL,
                total INTEGER NOT NULL,
                created REAL NOT NULL,
                status TEXT NOT NULL,
                booking_id TEXT
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id TEXT PRIMARY KEY,
                quote_id TEXT UNIQUE NOT NULL,
                trip TEXT NOT NULL,
                total INTEGER NOT NULL,
                status TEXT NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS booking_items (
                booking_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                rooms INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        conn.commit()


_init()


def _booked_rooms(conn: sqlite3.Connection, item_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(rooms), 0) AS n FROM booking_items "
        "WHERE item_id = ? AND status = 'confirmed'",
        (item_id,),
    ).fetchone()
    return row["n"]


def _validate(trip: dict, conn: sqlite3.Connection) -> list[str]:
    """Re-check a trip from scratch. Returns a list of problems, empty if it is safe to book."""
    if not isinstance(trip, dict) or not all(isinstance(i, dict) for i in trip.get("items", [])):
        return ["Malformed trip"]

    try:
        expected = plan_trip(trip.get("profile") or {})
    except (ValueError, TypeError) as exc:
        return [f"Invalid profile: {exc}"]

    sent = trip.get("items", [])
    if [i.get("item_id") for i in sent] != [i["item_id"] for i in expected["items"]]:
        return ["Items do not match the plan for this profile"]

    nights = expected["profile"]["nights"]
    errors = []

    for want, got in zip(expected["items"], sent):
        name = want["name"]

        if got.get("quantity") != want["quantity"] or got.get("unit_price") != want["unit_price"]:
            errors.append(f"{name}: quantity or list price was changed")
            continue

        price = got.get("final_unit_price")
        perks = got.get("perks", [])
        if not isinstance(price, int) or isinstance(price, bool) or not isinstance(perks, list):
            errors.append(f"{name}: invalid price or perks")
            continue

        # The same Rules Guard that checks every supplier offer checks the final price again.
        result = check_offer(want["item_id"], {"price": price, "perks": perks}, 1)
        if not result.ok:
            errors.append(f"{name}: " + "; ".join(result.violations))

        item = get_item(want["item_id"])
        if "rooms_available" in item:
            rooms = want["quantity"] // nights
            free = item["rooms_available"] - _booked_rooms(conn, want["item_id"])
            if rooms > free:
                errors.append(f"{name}: only {max(free, 0)} room(s) left")

    return errors


def create_quote(trip: dict) -> dict:
    """Validate a negotiated trip and hold it as a quote. Nothing is booked yet."""
    with closing(_connect()) as conn:
        errors = _validate(trip, conn)
        if errors:
            raise ValueError("; ".join(errors))

        expected = plan_trip(trip["profile"])
        lines = []
        for want, got in zip(expected["items"], trip["items"]):
            unit = got["final_unit_price"]
            lines.append(
                {
                    **want,
                    "final_unit_price": unit,
                    "final_total": unit * want["quantity"],
                    "perks": got.get("perks", []),
                }
            )

        # Totals are always recalculated here, never taken from the client.
        total = sum(line["final_total"] for line in lines)
        stored = {"profile": expected["profile"], "items": lines}
        quote_id = "Q-" + uuid.uuid4().hex[:10].upper()

        conn.execute(
            "INSERT INTO quotes (id, trip, total, created, status) VALUES (?, ?, ?, ?, 'open')",
            (quote_id, json.dumps(stored), total, time.time()),
        )
        conn.commit()

    return {
        "quote_id": quote_id,
        "total": total,
        "list_total": expected["list_total"],
        "saved": expected["list_total"] - total,
        "expires_in": QUOTE_TTL_SECONDS,
        "requires_confirmation": True,
    }


def get_booking(booking_id: str) -> dict:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise LookupError(f"Unknown booking: {booking_id}")

    trip = json.loads(row["trip"])
    return {
        "booking_id": row["id"],
        "status": row["status"],
        "total": row["total"],
        "created": row["created"],
        "voucher": {
            "profile": trip["profile"],
            "items": [
                {
                    "name": line["name"],
                    "quantity": line["quantity"],
                    "unit": line["unit"],
                    "final_unit_price": line["final_unit_price"],
                    "final_total": line["final_total"],
                    "perks": line["perks"],
                }
                for line in trip["items"]
            ],
        },
    }


def confirm_quote(quote_id: str) -> dict:
    """Turn a quote into a booking. Confirming the same quote twice returns the same booking."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")  # lock so two requests cannot grab the same last room
        row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
        if row is None:
            raise LookupError(f"Unknown quote: {quote_id}")

        if row["status"] == "booked":
            booking_id = row["booking_id"]
        else:
            if time.time() - row["created"] > QUOTE_TTL_SECONDS:
                raise ValueError("This quote has expired. Please request a new one.")

            trip = json.loads(row["trip"])
            errors = _validate(trip, conn)  # stock may have changed since the quote
            if errors:
                raise ValueError("; ".join(errors))

            booking_id = "SYN-" + uuid.uuid4().hex[:6].upper()
            nights = trip["profile"]["nights"]
            conn.execute(
                "INSERT INTO bookings (id, quote_id, trip, total, status, created) "
                "VALUES (?, ?, ?, ?, 'confirmed', ?)",
                (booking_id, quote_id, row["trip"], row["total"], time.time()),
            )
            for line in trip["items"]:
                if "rooms_available" in get_item(line["item_id"]):
                    conn.execute(
                        "INSERT INTO booking_items (booking_id, item_id, rooms, status) "
                        "VALUES (?, ?, ?, 'confirmed')",
                        (booking_id, line["item_id"], line["quantity"] // nights),
                    )
            conn.execute(
                "UPDATE quotes SET status = 'booked', booking_id = ? WHERE id = ?",
                (booking_id, quote_id),
            )
            conn.commit()

    return get_booking(booking_id)