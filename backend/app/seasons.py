"""Seasonal and holiday price levels for each destination.

Everything here is synthetic. The monthly curves describe typical busy and quiet
periods, not real market data. A factor of 1.0 means the usual year-round price.
"""
from datetime import date, timedelta

from app.inventory import DESTINATIONS

MIN_FACTOR = 0.55
MAX_FACTOR = 1.9
WEEKEND_PREMIUM = 1.10    # Friday and Saturday nights at leisure destinations
FLIGHT_SENSITIVITY = 0.6  # flights move less with the season than hotels do

FLAT = [1.0] * 12

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Price level for each month, January first.
MONTHLY = {
    "Delhi": [1.05, 1.10, 1.00, 0.90, 0.80, 0.75, 0.80, 0.85, 0.90, 1.05, 1.15, 1.15],
    "Agra": [1.10, 1.10, 0.95, 0.80, 0.70, 0.70, 0.75, 0.80, 0.90, 1.05, 1.20, 1.20],
    "Amritsar": [1.00, 1.05, 1.10, 0.95, 0.85, 0.80, 0.85, 0.90, 0.95, 1.10, 1.15, 1.05],
    "Manali": [1.20, 1.00, 0.95, 1.15, 1.30, 1.25, 0.90, 0.85, 0.90, 1.00, 0.90, 1.25],
    "Rishikesh": [0.90, 1.05, 1.15, 1.10, 0.95, 0.85, 0.75, 0.75, 1.05, 1.20, 1.15, 0.95],
    "Leh": [0.60, 0.60, 0.65, 0.80, 1.10, 1.30, 1.35, 1.30, 1.20, 0.95, 0.65, 0.60],
    "Jaipur": [1.15, 1.15, 1.00, 0.85, 0.75, 0.70, 0.75, 0.80, 0.90, 1.10, 1.20, 1.25],
    "Udaipur": [1.15, 1.15, 1.05, 0.90, 0.80, 0.75, 0.85, 0.85, 0.95, 1.10, 1.20, 1.25],
    "Mumbai": [1.05, 1.10, 1.05, 0.95, 0.90, 0.80, 0.80, 0.85, 0.90, 1.00, 1.10, 1.15],
    "Goa": [1.25, 1.15, 1.00, 0.90, 0.85, 0.70, 0.65, 0.70, 0.75, 0.95, 1.15, 1.35],
    "Varanasi": [1.05, 1.10, 1.05, 0.90, 0.75, 0.70, 0.70, 0.75, 0.90, 1.10, 1.20, 1.15],
    "Kolkata": [1.10, 1.10, 1.00, 0.90, 0.80, 0.75, 0.75, 0.80, 0.90, 1.25, 1.15, 1.15],
    "Darjeeling": [0.85, 0.95, 1.15, 1.30, 1.25, 0.80, 0.70, 0.70, 0.90, 1.25, 1.20, 0.95],
    "Kerala": [1.15, 1.10, 1.00, 0.95, 0.85, 0.75, 0.75, 0.80, 0.90, 1.00, 1.10, 1.25],
    "Andaman": [1.20, 1.15, 1.10, 1.00, 0.85, 0.70, 0.65, 0.65, 0.75, 0.95, 1.10, 1.30],
    "Meghalaya": [1.00, 1.05, 1.10, 1.15, 1.05, 0.80, 0.75, 0.75, 0.85, 1.20, 1.20, 1.10],
}

# Windows that repeat every year: (start month, day), (end month, day), factor, name.
YEARLY_EVENTS = [
    ((12, 24), (1, 1), 1.25, "Year-end holidays"),
    ((1, 24), (1, 26), 1.10, "Republic Day long weekend"),
    ((8, 14), (8, 16), 1.10, "Independence Day long weekend"),
]

# One-off windows. Edit or extend as you like.
DATED_EVENTS = [
    (date(2026, 11, 6), date(2026, 11, 10), 1.15, "Diwali week (approximate)"),
]


def _is_hub(destination: str) -> bool:
    return bool(DESTINATIONS.get(destination, {}).get("hub", False))


def event_factor(day: date) -> tuple[float, str | None]:
    """The strongest holiday uplift on this day, and its name."""
    best, name = 1.0, None
    month_day = (day.month, day.day)

    for start, end, factor, label in YEARLY_EVENTS:
        inside = start <= month_day <= end if start <= end else month_day >= start or month_day <= end
        if inside and factor > best:
            best, name = factor, label

    for start, end, factor, label in DATED_EVENTS:
        if start <= day <= end and factor > best:
            best, name = factor, label

    return best, name


def day_factor(destination: str, day: date, weekend: bool = True) -> float:
    """Price level for one night in a destination. 1.0 is the usual year-round price."""
    months = MONTHLY.get(destination, FLAT)
    factor = months[day.month - 1] * event_factor(day)[0]
    if weekend and day.weekday() in (4, 5) and not _is_hub(destination):  # Friday, Saturday
        factor *= WEEKEND_PREMIUM
    return min(MAX_FACTOR, max(MIN_FACTOR, factor))


def hotel_factor(destination: str, start: date, nights: int) -> float:
    """Average nightly price level across the whole stay."""
    nights = max(1, nights)
    total = sum(day_factor(destination, start + timedelta(days=i)) for i in range(nights))
    return total / nights


def flight_factor(destination: str, start: date, nights: int) -> float:
    """Flights follow the season more gently than hotels, and ignore weekends."""
    out = day_factor(destination, start, weekend=False)
    back = day_factor(destination, start + timedelta(days=max(1, nights)), weekend=False)
    return 1 + FLIGHT_SENSITIVITY * ((out + back) / 2 - 1)


def adjust(price: int, factor: float) -> int:
    """Apply a factor and round to the nearest 50 rupees, never below 50."""
    return max(50, int(round(price * factor / 50)) * 50)


def label(factor: float) -> str:
    if factor >= 1.25:
        return "peak season"
    if factor >= 1.08:
        return "busy season"
    if factor >= 0.92:
        return "regular season"
    return "quiet season"


def stay_info(destination: str, start: date, nights: int) -> dict:
    """A summary of the stay's dates and season, for the planner and the screen."""
    factor = hotel_factor(destination, start, nights)
    days = [start + timedelta(days=i) for i in range(max(1, nights))]
    events = sorted({event_factor(day)[1] for day in days} - {None})
    return {
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=nights)).isoformat(),
        "nights": nights,
        "hotel_factor": round(factor, 3),
        "hotel_change_pct": round((factor - 1) * 100),
        "season": label(factor),
        "events": events,
    }


def _window(start: tuple[int, int], end: tuple[int, int]) -> str:
    return f"{start[1]} {MONTH_NAMES[start[0] - 1][:3]} to {end[1]} {MONTH_NAMES[end[0] - 1][:3]}"


def calendar(destination: str) -> dict:
    """Twelve months of price levels plus the holiday windows, for the price calendar."""
    levels = MONTHLY.get(destination, FLAT)
    months = [
        {
            "month": number,
            "name": MONTH_NAMES[number - 1],
            "factor": factor,
            "change_pct": round((factor - 1) * 100),
            "season": label(factor),
        }
        for number, factor in enumerate(levels, start=1)
    ]

    events = [
        {"name": name, "factor": factor, "window": _window(start, end), "repeats": "every year"}
        for start, end, factor, name in YEARLY_EVENTS
    ]
    events += [
        {
            "name": name,
            "factor": factor,
            "window": f"{start.day} {MONTH_NAMES[start.month - 1][:3]} {start.year} to "
                      f"{end.day} {MONTH_NAMES[end.month - 1][:3]} {end.year}",
            "repeats": "one-off",
        }
        for start, end, factor, name in DATED_EVENTS
    ]

    return {
        "destination": destination,
        "months": months,
        "cheapest_month": min(months, key=lambda m: m["factor"])["name"],
        "busiest_month": max(months, key=lambda m: m["factor"])["name"],
        "weekend_premium_pct": 0 if _is_hub(destination) else round((WEEKEND_PREMIUM - 1) * 100),
        "events": events,
    }