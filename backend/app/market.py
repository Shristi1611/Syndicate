"""A small simulated market: other travellers fill rooms, shocks move demand, prices follow.

Everything here is synthetic and deterministic: the same seed always gives the same market.
The numbers are rules I chose for the demo, not real market data.
"""
import hashlib
import json
import time
from contextlib import closing
from datetime import date, timedelta

from app import seasons
from app.config import settings
from app.inventory import DESTINATIONS

SHOCK_LEVELS = {"surge": 1.35, "slump": 0.65}  # multiplies a destination's demand

BASE_OCC_MIN = 0.15
BASE_OCC_MAX = 0.85
NEUTRAL_OCC = 0.60     # at this occupancy the price is unchanged
PRESSURE_SLOPE = 0.6   # how strongly occupancy moves the price
MIN_PRESSURE = 0.90
MAX_PRESSURE = 1.30


def _connect():
    # Imported here because bookings imports the planner, which imports this module.
    from app import bookings

    return bookings._connect()


def _jitter(hotel_id: str, day: date) -> float:
    """A fixed wobble between -0.10 and +0.10 for one hotel on one night."""
    digest = hashlib.sha256(f"{settings.market_seed}:{hotel_id}:{day.isoformat()}".encode()).hexdigest()
    return (int(digest[:8], 16) % 21 - 10) / 100


class Snapshot:
    """The market as it stands right now. Load once, then ask it as many questions as needed."""

    def __init__(self, shocks: dict[str, float], stays: dict[str, list]):
        self.shocks = shocks  # {destination: demand level}
        self.stays = stays    # {hotel_id: [(rooms, first night, nights), ...]} from our own bookings

    def demand(self, destination: str) -> float:
        return self.shocks.get(destination, 1.0)

    def market_taken(self, hotel: dict, day: date) -> int:
        """Rooms held by simulated other travellers on one night."""
        factor = seasons.day_factor(hotel["destination"], day)
        base = min(BASE_OCC_MAX, max(BASE_OCC_MIN, 0.20 + 0.40 * factor)) + _jitter(hotel["id"], day)
        occupancy = min(1.0, max(0.0, base * self.demand(hotel["destination"])))
        total = hotel["rooms_available"]
        return min(total, int(total * occupancy))

    def _ours(self, hotel: dict, day: date) -> int:
        used = 0
        for rooms, first, nights in self.stays.get(hotel["id"], []):
            if first <= day < first + timedelta(days=nights):
                used += rooms
        return used

    def free_on(self, hotel: dict, day: date) -> int:
        return max(0, hotel["rooms_available"] - self.market_taken(hotel, day) - self._ours(hotel, day))

    def free_rooms(self, hotel: dict, start: date, nights: int) -> int:
        """Rooms free on every night of the stay."""
        return min(self.free_on(hotel, start + timedelta(days=i)) for i in range(max(1, nights)))

    def occupancy(self, hotel: dict, start: date, nights: int) -> float:
        """Average share of rooms taken across the stay, from 0 to 1."""
        total = hotel["rooms_available"]
        nights = max(1, nights)
        used = sum(total - self.free_on(hotel, start + timedelta(days=i)) for i in range(nights))
        return used / (total * nights)

    def price_pressure(self, hotel: dict, start: date, nights: int) -> float:
        """A fuller hotel costs more and an emptier one costs less."""
        occupancy = self.occupancy(hotel, start, nights)
        return min(MAX_PRESSURE, max(MIN_PRESSURE, 1 + PRESSURE_SLOPE * (occupancy - NEUTRAL_OCC)))


def snapshot() -> Snapshot:
    """Read the current shocks and our own dated bookings."""
    with closing(_connect()) as conn:
        shocks = {
            row["destination"]: row["level"]
            for row in conn.execute("SELECT destination, level FROM market_shocks")
        }
        stays: dict[str, list] = {}
        rows = conn.execute(
            "SELECT bi.item_id, bi.rooms, b.trip FROM booking_items bi "
            "JOIN bookings b ON b.id = bi.booking_id "
            "WHERE bi.status = 'confirmed' AND b.status = 'confirmed'"
        ).fetchall()
        for row in rows:
            profile = json.loads(row["trip"]).get("profile", {})
            first = profile.get("start_date")
            if not first:  # undated bookings have no nights to count
                continue
            stays.setdefault(row["item_id"], []).append(
                (row["rooms"], date.fromisoformat(first), profile["nights"])
            )
    return Snapshot(shocks, stays)


# ------------------------------------------------------------ judge controls


def state() -> dict:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT destination, kind, level, created FROM market_shocks ORDER BY created"
        ).fetchall()
    return {"enabled": settings.market_enabled, "shocks": [dict(row) for row in rows]}


def set_shock(destination: str, kind: str) -> None:
    """Make a destination busier (surge) or quieter (slump). A new shock replaces the old one."""
    if destination not in DESTINATIONS:
        raise LookupError(f"Unknown destination: {destination}")
    if kind not in SHOCK_LEVELS:
        raise ValueError(f"Unknown shock: {kind}. Use surge or slump.")
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO market_shocks (destination, kind, level, created) VALUES (?, ?, ?, ?)",
            (destination, kind, SHOCK_LEVELS[kind], time.time()),
        )
        conn.commit()


def clear_shocks() -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM market_shocks")
        conn.commit()


def availability(hotel: dict, start: date, nights: int) -> dict:
    """Night-by-night free rooms for one hotel, for the screen."""
    snap = snapshot() if settings.market_enabled else None
    days = [start + timedelta(days=i) for i in range(nights)]
    nightly = [
        {
            "date": day.isoformat(),
            "free_rooms": snap.free_on(hotel, day) if snap else hotel["rooms_available"],
        }
        for day in days
    ]
    return {
        "hotel_id": hotel["id"],
        "name": hotel["name"],
        "start_date": start.isoformat(),
        "nights": nights,
        "market_enabled": settings.market_enabled,
        "total_rooms": hotel["rooms_available"],
        "nightly": nightly,
        "free_rooms": min(night["free_rooms"] for night in nightly),
        "occupancy_pct": round(100 * snap.occupancy(hotel, start, nights)) if snap else None,
        "price_pressure_pct": round((snap.price_pressure(hotel, start, nights) - 1) * 100) if snap else None,
    }