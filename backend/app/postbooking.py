import json
import sqlite3
import time
from contextlib import closing

from app.bookings import _connect
from app.inventory import get_item, get_supplier

LATE_CANCEL_FEE = 0.5  # share of an item's price the supplier keeps inside its free-cancellation window


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cancellations (
            booking_id TEXT PRIMARY KEY,
            refund INTEGER NOT NULL,
            fee INTEGER NOT NULL,
            days_before_trip INTEGER NOT NULL,
            created REAL NOT NULL
        )
        """
    )


def _check_days(days_before_trip: int) -> None:
    if not isinstance(days_before_trip, int) or isinstance(days_before_trip, bool):
        raise ValueError("days_before_trip must be a whole number")
    if not 0 <= days_before_trip <= 365:
        raise ValueError("days_before_trip must be between 0 and 365")


def _breakdown(conn: sqlite3.Connection, booking_id: str, days_before_trip: int):
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None:
        raise LookupError(f"Unknown booking: {booking_id}")

    trip = json.loads(row["trip"])
    lines = []
    refund = 0
    for line in trip["items"]:
        supplier = get_supplier(get_item(line["item_id"])["supplier_id"])
        free = days_before_trip >= supplier["free_cancellation_days"]
        item_refund = line["final_total"] if free else round(line["final_total"] * (1 - LATE_CANCEL_FEE))
        refund += item_refund
        lines.append(
            {
                "name": line["name"],
                "paid": line["final_total"],
                "refund": item_refund,
                "fee": line["final_total"] - item_refund,
                "free_cancellation": free,
                "free_until_days_before": supplier["free_cancellation_days"],
            }
        )
    return row, lines, refund


def cancel_preview(booking_id: str, days_before_trip: int) -> dict:
    """Show what a cancellation would refund. Changes nothing."""
    _check_days(days_before_trip)
    with closing(_connect()) as conn:
        _ensure(conn)
        row, lines, refund = _breakdown(conn, booking_id, days_before_trip)
        if row["status"] == "cancelled":
            raise ValueError("This booking is already cancelled")
        return {
            "booking_id": booking_id,
            "days_before_trip": days_before_trip,
            "total_paid": row["total"],
            "refund": refund,
            "fee": row["total"] - refund,
            "lines": lines,
            "requires_confirmation": True,
        }


def cancel_confirm(booking_id: str, days_before_trip: int) -> dict:
    """Cancel the booking and free its rooms. Cancelling twice is safe."""
    _check_days(days_before_trip)
    with closing(_connect()) as conn:
        _ensure(conn)
        conn.execute("BEGIN IMMEDIATE")  # lock so two requests cannot cancel at the same time
        row, lines, refund = _breakdown(conn, booking_id, days_before_trip)

        if row["status"] == "cancelled":
            done = conn.execute(
                "SELECT * FROM cancellations WHERE booking_id = ?", (booking_id,)
            ).fetchone()
            return {
                "booking_id": booking_id,
                "status": "cancelled",
                "refund": done["refund"],
                "fee": done["fee"],
                "already_cancelled": True,
            }

        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        conn.execute(
            "UPDATE booking_items SET status = 'cancelled' WHERE booking_id = ?", (booking_id,)
        )
        conn.execute(
            "INSERT INTO cancellations (booking_id, refund, fee, days_before_trip, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (booking_id, refund, row["total"] - refund, days_before_trip, time.time()),
        )
        conn.commit()

    return {
        "booking_id": booking_id,
        "status": "cancelled",
        "refund": refund,
        "fee": row["total"] - refund,
        "lines": lines,
        "already_cancelled": False,
    }