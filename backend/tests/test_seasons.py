from datetime import date, timedelta

import pytest

from app import seasons

CITIES = {
    "Delhi", "Agra", "Amritsar", "Manali", "Rishikesh", "Leh", "Jaipur", "Udaipur",
    "Mumbai", "Goa", "Varanasi", "Kolkata", "Darjeeling", "Kerala", "Andaman", "Meghalaya",
}


def test_every_destination_has_a_twelve_month_curve():
    assert set(seasons.MONTHLY) == CITIES
    for name, months in seasons.MONTHLY.items():
        assert len(months) == 12, name


def test_factors_stay_in_bounds():
    first = date(2027, 1, 1)
    for city in seasons.MONTHLY:
        for offset in range(365):
            factor = seasons.day_factor(city, first + timedelta(days=offset))
            assert seasons.MIN_FACTOR <= factor <= seasons.MAX_FACTOR, (city, offset)


def test_goa_peaks_at_year_end_and_dips_in_the_monsoon():
    december = seasons.day_factor("Goa", date(2026, 12, 15), weekend=False)
    july = seasons.day_factor("Goa", date(2027, 7, 15), weekend=False)
    assert december > 1.3
    assert july < 0.7
    assert december > july


def test_year_end_event_lifts_prices():
    holiday = seasons.day_factor("Goa", date(2026, 12, 31), weekend=False)
    ordinary = seasons.day_factor("Goa", date(2026, 12, 10), weekend=False)
    assert holiday > ordinary


def test_event_lookup():
    assert seasons.event_factor(date(2026, 12, 31)) == (1.25, "Year-end holidays")
    assert seasons.event_factor(date(2027, 1, 1)) == (1.25, "Year-end holidays")  # the window wraps the year
    assert seasons.event_factor(date(2027, 5, 5)) == (1.0, None)


def test_weekend_premium_applies_to_leisure_destinations_only(monkeypatch):
    monkeypatch.setitem(seasons.DESTINATIONS, "Delhi", {"name": "Delhi", "hub": True})
    monkeypatch.setitem(seasons.DESTINATIONS, "Goa", {"name": "Goa"})

    first = date(2027, 3, 1)
    friday = first + timedelta(days=(4 - first.weekday()) % 7)
    monday = friday + timedelta(days=3)

    goa_friday = seasons.day_factor("Goa", friday)
    assert goa_friday == pytest.approx(seasons.day_factor("Goa", friday, weekend=False) * seasons.WEEKEND_PREMIUM)
    assert seasons.day_factor("Goa", monday) == seasons.day_factor("Goa", monday, weekend=False)
    assert seasons.day_factor("Delhi", friday) == seasons.day_factor("Delhi", friday, weekend=False)


def test_unknown_destination_has_a_flat_curve():
    assert seasons.day_factor("Atlantis", date(2027, 5, 5), weekend=False) == 1.0


def test_adjust_rounds_to_fifty():
    assert seasons.adjust(7000, 1.0) == 7000
    assert seasons.adjust(7000, 1.35) == 9450
    assert seasons.adjust(5800, 0.9) == 5200  # 5220 rounds to the nearest 50
    assert seasons.adjust(60, 0.55) == 50     # never below 50


def test_stay_info():
    info = seasons.stay_info("Goa", date(2026, 12, 28), 5)
    assert info["start_date"] == "2026-12-28"
    assert info["end_date"] == "2027-01-02"
    assert info["nights"] == 5
    assert "Year-end holidays" in info["events"]
    assert info["season"] == "peak season"
    assert info["hotel_change_pct"] > 25

    quiet = seasons.stay_info("Goa", date(2027, 7, 10), 4)
    assert quiet["season"] == "quiet season"
    assert quiet["hotel_change_pct"] < -20
    assert quiet["events"] == []


def test_flight_prices_move_less_than_hotels():
    hotels = seasons.hotel_factor("Goa", date(2026, 12, 20), 4)
    flights = seasons.flight_factor("Goa", date(2026, 12, 20), 4)
    assert 1 < flights < hotels