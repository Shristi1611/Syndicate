"""Generate the synthetic Indian travel catalogue.

Run from the backend folder:   python generate_catalogue.py
Optional:                      python generate_catalogue.py --out some\\folder --seed 7

Everything is fictional and comes from a fixed seed, so every run gives the same data.
"""
import argparse
import json
import random
from pathlib import Path

DEFAULT_SEED = 2026
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data"


def _round(value: float, step: int) -> int:
    return int(round(value / step) * step)


# --------------------------------------------------------------- destinations


def _d(name, code, region, kind, multiplier, lat, lon, hub, tagline, extra_tags=()):
    return {
        "name": name,
        "code": code,
        "region": region,
        "kind": kind,  # beach, hill, heritage or metro: decides which hotel types exist
        "multiplier": multiplier,  # price level compared with Goa
        "lat": lat,
        "lon": lon,
        "hub": hub,  # carries flights later
        "tagline": tagline,
        "extra_tags": list(extra_tags),
    }


DESTINATIONS = [
    _d("Delhi", "DEL", "North", "metro", 1.10, 28.61, 77.21, True, "Capital of empires, street food and late nights"),
    _d("Agra", "AGR", "North", "heritage", 0.90, 27.18, 78.01, False, "The Taj, Mughal gardens and marble inlay"),
    _d("Amritsar", "AMR", "North", "heritage", 0.85, 31.63, 74.87, False, "Golden Temple, langar and the Wagah border"),
    _d("Manali", "MAN", "Himalaya", "hill", 0.95, 32.24, 77.19, False, "Snow passes, river rafting and pine valleys"),
    _d("Rishikesh", "RSH", "Himalaya", "hill", 0.85, 30.09, 78.27, False, "Yoga, the Ganga and white-water rafting"),
    _d("Leh", "LEH", "Himalaya", "hill", 1.15, 34.15, 77.58, False, "High passes, monasteries and Pangong blue"),
    _d("Jaipur", "JAI", "West", "heritage", 1.00, 26.91, 75.79, False, "The Pink City of forts, bazaars and block prints"),
    _d("Udaipur", "UDA", "West", "heritage", 1.15, 24.59, 73.71, False, "Lake palaces and golden-hour boat rides"),
    _d("Mumbai", "MUM", "West", "metro", 1.25, 19.08, 72.88, True, "Maximum city: sea, cinema and street food"),
    _d("Goa", "GOA", "West", "beach", 1.00, 15.50, 73.83, False, "Beaches, Portuguese lanes and slow sunsets"),
    _d("Varanasi", "VAR", "Central", "heritage", 0.80, 25.32, 83.01, False, "Ancient ghats, dawn boat rides and silk"),
    _d("Kolkata", "KOL", "East", "heritage", 0.90, 22.57, 88.36, True, "Trams, sweets, colonial grandeur and art"),
    _d("Darjeeling", "DAR", "East", "hill", 0.90, 27.04, 88.26, False, "Tea hills, toy trains and Kanchenjunga sunrise"),
    _d("Kerala", "KER", "South", "beach", 1.05, 9.93, 76.27, False, "Backwaters, spice hills and Ayurveda", ["backwaters"]),
    _d("Andaman", "AND", "Islands", "beach", 1.30, 11.62, 92.73, False, "Turquoise water, coral reefs and white sand"),
    _d("Meghalaya", "MEG", "North-East", "hill", 0.85, 25.57, 91.88, False, "Living root bridges, waterfalls and cloud-top villages"),
]

# Per person, per trip. Remote places cost more to reach.
TRANSFER_PRICE = {
    "Leh": 2200, "Andaman": 1800, "Manali": 1600, "Meghalaya": 1500,
    "Darjeeling": 1400, "Rishikesh": 1100, "Kerala": 1000, "Goa": 900, "Udaipur": 900,
}

# ------------------------------------------------------------------ suppliers
# id, name, personality, floor_ratio, tradeable perks, patience rounds, free-cancellation days

SUPPLIERS = [
    ("S_01", "Coastline Stays", "firm and businesslike, rarely drops the price, prefers to add small perks instead", 0.90, ["free_breakfast"], 2, 3),
    ("S_02", "Heritage Hospitality", "warm and flexible, loves long stays and will bundle extras to win them", 0.80, ["longer_stay_discount", "free_breakfast", "airport_transfer"], 4, 7),
    ("S_03", "Palm Group", "enthusiastic dealmaker who gets generous when you book a package", 0.78, ["longer_stay_discount", "airport_transfer", "late_checkout"], 4, 5),
    ("S_04", "Urban Nest", "modern and quick, gives discounts for early payment but not for much else", 0.85, ["early_payment_discount", "late_checkout"], 3, 2),
    ("S_05", "Summit Hospitality", "practical hill specialists who reward multi-night stays", 0.83, ["longer_stay_discount", "free_breakfast"], 3, 6),
    ("S_06", "Riverbend Resorts", "relaxed and generous, especially for travellers who are flexible on dates", 0.76, ["free_upgrade", "longer_stay_discount", "free_breakfast"], 4, 8),
    ("S_07", "Crown and Court Hotels", "formal and premium, rarely discounts and protects its rates", 0.91, ["late_checkout", "free_upgrade"], 2, 10),
    ("S_08", "Monsoon Stays", "chatty and generous with perks but firm on the headline price", 0.88, ["free_breakfast", "airport_transfer", "late_checkout"], 3, 4),
    ("S_09", "Lotus Collection", "boutique curator who rewards early commitment", 0.82, ["free_upgrade", "early_payment_discount"], 3, 5),
    ("S_10", "Backroads Lodging", "budget-friendly and a hard haggler who respects a firm counter", 0.74, ["longer_stay_discount", "group_discount"], 4, 2),
    ("S_11", "Trailhead Experiences", "friendly local guides who reward groups and repeat bookings", 0.82, ["group_discount", "free_upgrade"], 3, 4),
    ("S_12", "Wayfarer Tours", "efficient operator who likes simple, clean deals", 0.85, ["group_discount", "early_payment_discount"], 3, 3),
    ("S_13", "Local Roots", "community-run and fair, will trade a discount for a bigger group", 0.79, ["group_discount"], 4, 5),
    ("S_14", "Skyline Adventures", "thrill specialists with premium pricing and little patience", 0.88, ["early_payment_discount", "free_upgrade"], 2, 3),
    ("S_15", "Spice Route Culinary", "food lovers who get flexible when guests are enthusiastic", 0.80, ["group_discount", "free_upgrade"], 4, 4),
    ("S_16", "Serene Journeys", "calm wellness and culture host, generous with upgrades", 0.84, ["free_upgrade", "early_payment_discount"], 3, 6),
    ("S_17", "Roadrunner Transfers", "volume transfer operator who offers discounts for bigger bookings", 0.86, ["group_discount", "early_payment_discount"], 3, 2),
    ("S_18", "Dawn Chauffeurs", "premium cars and drivers, firm on price, will upgrade the vehicle", 0.89, ["free_upgrade"], 2, 3),
]
HOTEL_SUPPLIERS = [s[0] for s in SUPPLIERS[:10]]
CATEGORY_SUPPLIERS = {
    "sightseeing": ["S_11", "S_12", "S_13"],
    "culture": ["S_13", "S_15", "S_16"],
    "dining": ["S_15"],
    "adventure": ["S_14", "S_11"],
    "wellness": ["S_16"],
    "nature": ["S_11", "S_13"],
    "transfer": ["S_17", "S_18"],
}

# --------------------------------------------------------------------- hotels
# key: star, name endings, tags, price range per night (Goa level), rooms range, chance of step-free

ARCH_ORDER = ["luxury", "boutique", "family", "mid", "budget"]

ARCHETYPES = {
    "beach": {
        "luxury": (5, ["Resort", "Beach Resort", "Spa Resort"], ["luxury", "beachfront", "spa", "romantic", "pool"], (10500, 16000), (4, 8), 0.90),
        "boutique": (4, ["Retreat", "Cove", "Villas"], ["quiet", "beachfront", "romantic", "boutique"], (5200, 7800), (4, 7), 0.60),
        "family": (4, ["Family Resort", "Gardens", "Bay Resort"], ["family", "pool", "quiet", "food"], (5000, 7400), (6, 10), 0.85),
        "mid": (3, ["Hotel", "Beach Inn", "Suites"], ["lively", "nightlife", "central"], (2800, 4200), (8, 14), 0.35),
        "budget": (2, ["Stay", "Hostel", "Lodge"], ["budget", "lively", "nightlife"], (1400, 2400), (10, 20), 0.10),
    },
    "hill": {
        "luxury": (5, ["Mountain Resort", "Lodge and Spa", "Valley Resort"], ["luxury", "views", "spa", "romantic", "mountain"], (9500, 14500), (4, 8), 0.85),
        "boutique": (4, ["Chalet", "Retreat", "Cottages"], ["quiet", "views", "boutique", "garden", "mountain"], (5000, 7500), (4, 7), 0.45),
        "family": (4, ["Garden Hotel", "Valley Lodge", "Hillside Resort"], ["family", "quiet", "garden", "food", "views"], (4800, 7000), (6, 10), 0.80),
        "mid": (3, ["Inn", "Lodge", "Hotel"], ["central", "lively", "views"], (2600, 4000), (8, 14), 0.30),
        "budget": (2, ["Homestay", "Hostel", "Stay"], ["budget", "lively", "mountain"], (1300, 2300), (8, 18), 0.10),
    },
    "heritage": {
        "luxury": (5, ["Palace", "Mahal", "Grand Palace"], ["heritage", "luxury", "pool", "romantic", "spa"], (10000, 15500), (4, 8), 0.90),
        "boutique": (4, ["Haveli", "Kothi", "House"], ["heritage", "quiet", "boutique", "garden", "romantic"], (5200, 7800), (4, 7), 0.55),
        "family": (4, ["Residency", "Garden Hotel", "Courtyard"], ["family", "quiet", "pool", "food", "garden"], (5000, 7300), (6, 10), 0.85),
        "mid": (3, ["Inn", "Hotel", "Suites"], ["central", "lively", "heritage"], (2700, 4100), (8, 14), 0.35),
        "budget": (2, ["Hostel", "Guesthouse", "Stay"], ["budget", "central", "lively"], (1300, 2300), (10, 20), 0.10),
    },
    "metro": {
        "luxury": (5, ["Grand", "Towers", "Residences"], ["luxury", "spa", "pool", "central", "romantic"], (11000, 16500), (6, 12), 0.95),
        "boutique": (4, ["Boutique Hotel", "House", "Rooftop Hotel"], ["boutique", "central", "rooftop", "quiet"], (5400, 8000), (5, 9), 0.65),
        "family": (4, ["Suites", "Residency", "Park Hotel"], ["family", "quiet", "pool", "food", "central"], (5200, 7600), (8, 14), 0.90),
        "mid": (3, ["Inn", "Hotel", "Lodge"], ["central", "lively", "budget"], (3000, 4500), (10, 18), 0.50),
        "budget": (2, ["Hostel", "Stay", "Rooms"], ["budget", "central", "lively", "nightlife"], (1500, 2600), (12, 24), 0.20),
    },
}

PREFIXES = {
    "beach": ["Coral", "Palm", "Azure", "Dune", "Tide", "Cashew", "Sandpiper", "Lagoon", "Monsoon", "Seashell",
              "Driftwood", "Sunset", "Cove", "Mango", "Tamarind", "Pelican", "Surf", "Breeze", "Saltwater", "Coconut"],
    "hill": ["Cedar", "Pine", "Deodar", "Misty", "Alpine", "Snowline", "Rhododendron", "Cloud", "Juniper", "Orchid",
             "Ridge", "Valley", "Pinecrest", "Larch", "Highland", "Frost", "Meadow", "Summit", "Aspen", "Sunrise"],
    "heritage": ["Saffron", "Marigold", "Peacock", "Lotus", "Jasmine", "Amber", "Indigo", "Sandalwood", "Mehfil", "Kesar",
                 "Rani", "Nawab", "Garden", "Mughal", "Courtyard", "Turmeric", "Cardamom", "Rose", "Zari", "Chinar"],
    "metro": ["Metro", "Skyline", "Central", "Harbour", "Crown", "Meridian", "Banyan", "Orchid", "Pearl", "Capital",
              "Gateway", "Opal", "Zenith", "Atlas", "Neon", "Cinnabar", "Monsoon", "Lantern", "Ivory", "Indus"],
}

# ----------------------------------------------------------------- experiences
# name, category, tags, step-free, hours, price per person (Goa level)

SIGNATURES = {
    "Delhi": [
        ("Old Delhi Heritage Walk", "sightseeing", ["heritage", "lively"], False, 3, 1200),
        ("Humayun's Tomb and Gardens Tour", "sightseeing", ["heritage", "quiet"], True, 3, 1500),
        ("Chandni Chowk Food Trail", "dining", ["food", "lively"], False, 3, 1400),
        ("Qutub Minar Evening Visit", "sightseeing", ["heritage", "quiet", "romantic"], True, 2, 1300),
        ("Street Art and Craft Market Tour", "culture", ["culture", "budget"], True, 3, 1100),
        ("Cycling Through Lutyens' Delhi", "adventure", ["adventure", "nature"], True, 3, 1600),
    ],
    "Agra": [
        ("Taj Mahal Sunrise Guided Visit", "sightseeing", ["heritage", "romantic"], True, 3, 2200),
        ("Agra Fort Guided Tour", "sightseeing", ["heritage"], False, 3, 1500),
        ("Mehtab Bagh Sunset Viewing", "sightseeing", ["quiet", "romantic"], True, 2, 1100),
        ("Mughal Cooking Class", "culture", ["food", "culture"], True, 3, 1900),
        ("Fatehpur Sikri Day Trip", "sightseeing", ["heritage"], False, 6, 2400),
        ("Old City Bazaar Walk", "culture", ["lively", "budget"], False, 2, 900),
    ],
    "Amritsar": [
        ("Golden Temple Evening Visit", "culture", ["heritage", "quiet"], True, 3, 900),
        ("Wagah Border Ceremony", "culture", ["lively", "family"], False, 4, 1300),
        ("Jallianwala Bagh and Old City Walk", "sightseeing", ["heritage"], True, 3, 1100),
        ("Kulcha and Langar Food Trail", "dining", ["food", "budget"], True, 3, 1000),
        ("Phulkari Craft Workshop", "culture", ["culture", "quiet"], True, 3, 1400),
        ("Village Dhaba Sunset Dinner", "dining", ["romantic", "family"], True, 3, 2200),
    ],
    "Manali": [
        ("Rohtang Pass Day Trip", "adventure", ["mountain", "views"], False, 9, 3500),
        ("Solang Valley Paragliding", "adventure", ["views", "adventure"], False, 2, 3200),
        ("Old Manali Cafe Trail", "dining", ["lively", "budget"], True, 3, 1200),
        ("Hadimba Temple Forest Walk", "sightseeing", ["quiet", "nature"], False, 3, 900),
        ("Beas River Rafting", "adventure", ["water", "adventure"], False, 3, 1800),
        ("Apple Orchard Picnic", "nature", ["family", "quiet"], True, 3, 1500),
    ],
    "Rishikesh": [
        ("Ganga Aarti at Triveni Ghat", "culture", ["quiet", "culture"], False, 2, 600),
        ("Morning Yoga by the Ganga", "wellness", ["quiet", "wellness"], True, 2, 1200),
        ("Ganga River Rafting", "adventure", ["water", "adventure"], False, 3, 1800),
        ("Bungee and Flying Fox", "adventure", ["adventure", "lively"], False, 3, 3600),
        ("Beatles Ashram Walk", "sightseeing", ["heritage", "quiet"], False, 3, 800),
        ("Himalayan Sound Healing Session", "wellness", ["quiet", "wellness"], True, 2, 1800),
    ],
    "Leh": [
        ("Pangong Lake Camp Experience", "adventure", ["views", "mountain"], False, 24, 8500),
        ("Thiksey and Hemis Monastery Circuit", "culture", ["heritage", "quiet"], False, 8, 3200),
        ("Khardung La Drive", "adventure", ["mountain", "views"], False, 8, 4500),
        ("Shanti Stupa Sunset by Road", "sightseeing", ["quiet", "romantic"], True, 2, 900),
        ("Indus River Rafting", "adventure", ["water", "adventure"], False, 3, 2600),
        ("Ladakhi Kitchen Cooking Class", "culture", ["food", "culture"], True, 3, 2000),
    ],
    "Jaipur": [
        ("Amber Fort Guided Tour", "sightseeing", ["heritage"], False, 4, 1600),
        ("City Palace Evening Visit", "sightseeing", ["heritage", "quiet", "luxury"], True, 3, 3200),
        ("Old City Food Trail", "dining", ["food", "lively", "budget"], True, 3, 1100),
        ("Sunrise Hot Air Balloon", "adventure", ["romantic", "views"], False, 2, 4500),
        ("Block Printing Workshop", "culture", ["quiet", "culture"], True, 3, 1400),
        ("Rajasthani Folk Dinner and Puppet Show", "dining", ["family", "culture"], True, 3, 2000),
    ],
    "Udaipur": [
        ("Lake Pichola Sunset Boat Ride", "sightseeing", ["romantic", "water", "quiet"], False, 2, 1800),
        ("City Palace Guided Tour", "sightseeing", ["heritage"], False, 3, 1700),
        ("Heritage Haveli Dinner", "dining", ["romantic", "luxury"], True, 3, 3800),
        ("Cooking Class with a Local Family", "culture", ["food", "culture"], True, 3, 2200),
        ("Monsoon Palace Sunset Drive", "sightseeing", ["views", "quiet"], True, 3, 1500),
        ("Miniature Painting Workshop", "culture", ["quiet", "culture"], True, 3, 1600),
    ],
    "Mumbai": [
        ("Colaba Heritage Walk", "sightseeing", ["heritage"], False, 3, 1300),
        ("Elephanta Caves Ferry Trip", "sightseeing", ["heritage", "water"], False, 5, 1900),
        ("Bandra Street Food Trail", "dining", ["food", "lively"], True, 3, 1700),
        ("Dharavi Community Tour", "culture", ["culture"], True, 3, 1500),
        ("Film Studio Tour", "culture", ["lively", "family"], True, 4, 2400),
        ("Marine Drive Sunset Dinner Cruise", "dining", ["romantic", "water"], True, 3, 3600),
    ],
    "Goa": [
        ("Old Goa Heritage Walk", "sightseeing", ["heritage", "quiet"], True, 3, 1200),
        ("Spice Plantation Tour with Lunch", "nature", ["family", "food", "quiet"], True, 5, 1800),
        ("Dolphin Spotting Boat Ride", "adventure", ["lively", "water", "family"], False, 2, 1500),
        ("Sunset Beach Dinner", "dining", ["romantic", "quiet", "beachfront"], True, 3, 2500),
        ("Mandovi River Sunset Cruise", "sightseeing", ["romantic", "water"], True, 2, 1700),
        ("Goan Kitchen Cooking Class", "culture", ["food", "culture"], True, 3, 2000),
    ],
    "Varanasi": [
        ("Sunrise Boat Ride on the Ganga", "culture", ["heritage", "quiet", "water"], False, 2, 1000),
        ("Evening Ganga Aarti from a Boat", "culture", ["quiet", "culture"], True, 2, 1100),
        ("Old City Lanes Heritage Walk", "sightseeing", ["heritage"], False, 3, 800),
        ("Sarnath Guided Tour", "sightseeing", ["heritage", "quiet"], True, 4, 1500),
        ("Banarasi Silk Weaving Visit", "culture", ["culture"], True, 2, 900),
        ("Kachori Gali Food Trail", "dining", ["food", "budget"], False, 3, 900),
    ],
    "Kolkata": [
        ("North Kolkata Heritage Walk", "sightseeing", ["heritage"], False, 3, 1100),
        ("Victoria Memorial and Maidan Tour", "sightseeing", ["heritage", "quiet"], True, 3, 1300),
        ("Howrah Bridge and Flower Market Dawn Walk", "culture", ["culture", "lively"], False, 3, 900),
        ("Bengali Sweets and Street Food Trail", "dining", ["food", "lively"], True, 3, 1400),
        ("Hooghly River Sunset Cruise", "sightseeing", ["romantic", "water"], True, 2, 1500),
        ("Kumartuli Idol Studio Visit", "culture", ["culture", "quiet"], False, 2, 800),
    ],
    "Darjeeling": [
        ("Tiger Hill Sunrise Drive", "sightseeing", ["views", "mountain"], False, 4, 1400),
        ("Toy Train Joyride", "sightseeing", ["family", "heritage"], False, 2, 1500),
        ("Tea Estate Walk and Tasting", "nature", ["quiet", "nature"], True, 3, 1300),
        ("Mountaineering Institute Tour", "sightseeing", ["mountain", "heritage"], False, 3, 700),
        ("Monastery and Peace Pagoda Visit", "culture", ["quiet", "culture"], False, 3, 1000),
        ("Momos and Tea Cooking Class", "culture", ["food", "culture"], True, 3, 1700),
    ],
    "Kerala": [
        ("Alleppey Houseboat Day Cruise", "sightseeing", ["romantic", "water", "quiet", "backwaters"], True, 6, 3500),
        ("Munnar Tea Plantation Walk", "nature", ["quiet", "nature"], False, 3, 1100),
        ("Kathakali Performance Evening", "culture", ["culture", "heritage"], True, 2, 1000),
        ("Ayurvedic Massage and Wellness Session", "wellness", ["quiet", "wellness"], True, 2, 2800),
        ("Kerala Sadya Cooking Class", "culture", ["food", "culture"], True, 3, 1800),
        ("Periyar Wildlife Boat Safari", "nature", ["water", "family", "nature"], False, 3, 1700),
    ],
    "Andaman": [
        ("Radhanagar Beach Sunset", "sightseeing", ["beachfront", "quiet", "romantic"], True, 3, 900),
        ("Discovery Scuba Dive", "adventure", ["water", "adventure"], False, 3, 5500),
        ("Glass-Bottom Boat Trip", "sightseeing", ["water", "family"], True, 2, 1600),
        ("Ross Island Heritage Ferry", "sightseeing", ["heritage", "water"], False, 4, 1400),
        ("Mangrove Kayaking", "adventure", ["water", "nature", "adventure"], False, 3, 2400),
        ("Beachside Seafood Dinner", "dining", ["romantic", "beachfront", "food"], True, 3, 2800),
    ],
    "Meghalaya": [
        ("Living Root Bridges Trek", "adventure", ["nature", "adventure"], False, 6, 2600),
        ("Dawki Crystal River Boat Ride", "nature", ["water", "quiet", "nature"], True, 3, 1800),
        ("Cherrapunji Waterfalls Tour", "sightseeing", ["views", "nature"], False, 6, 2000),
        ("Mawlynnong Village Day Trip", "culture", ["quiet", "culture"], True, 6, 2200),
        ("Mawsmai Caving", "adventure", ["adventure"], False, 3, 1500),
        ("Khasi Kitchen Lunch Experience", "dining", ["food", "culture"], True, 3, 1600),
    ],
}

PERSONAS = [
    {
        "id": "honeymoon",
        "name": "Honeymoon couple",
        "tagline": "Privacy, views and a touch of luxury",
        "profile": {"destination": "Goa", "nights": 4, "travellers": 2, "budget_total": 150000,
                    "stairs_free": False, "interests": ["romantic", "luxury", "beachfront"]},
    },
    {
        "id": "family",
        "name": "Family with a grandmother",
        "tagline": "Step-free, relaxed and good food",
        "profile": {"destination": "Goa", "nights": 5, "travellers": 5, "budget_total": 150000,
                    "stairs_free": True, "interests": ["family", "food", "quiet"]},
    },
    {
        "id": "backpacker",
        "name": "Solo budget backpacker",
        "tagline": "Cheapest beds and lively nights",
        "profile": {"destination": "Goa", "nights": 5, "travellers": 1, "budget_total": 40000,
                    "stairs_free": False, "interests": ["lively", "nightlife", "budget"]},
    },
]


# ------------------------------------------------------------------ generation


def _hotel_name(rng: random.Random, kind: str, nouns: list[str], used: set[str]) -> str:
    prefixes = PREFIXES[kind]
    for _ in range(60):
        name = f"{rng.choice(prefixes)} {rng.choice(nouns)}"
        if name not in used:
            used.add(name)
            return name
    base = f"{rng.choice(prefixes)} {rng.choice(nouns)}"
    number = 2
    while f"{base} {number}" in used:
        number += 1
    name = f"{base} {number}"
    used.add(name)
    return name


def _make_hotels(rng: random.Random, dest: dict, used_names: set[str]) -> list[dict]:
    kind = dest["kind"]
    counts = {"luxury": 1, "boutique": 2, "family": 2, "mid": 2, "budget": 1}
    for key in rng.sample(["luxury", "boutique", "mid", "budget"], rng.randint(0, 2)):
        counts[key] += 1  # 8 to 10 hotels per destination

    hotels = []
    for key in ARCH_ORDER:
        star, nouns, tags, (pmin, pmax), (rmin, rmax), step_free_chance = ARCHETYPES[kind][key]
        for i in range(counts[key]):
            price = _round(rng.uniform(pmin, pmax) * dest["multiplier"], 100)
            step_free = rng.random() < step_free_chance
            if key == "family" and i == 0:
                step_free = True  # every destination has a step-free family hotel
            hotels.append(
                {
                    "id": f"H_{dest['code']}_{len(hotels) + 1:02d}",
                    "name": _hotel_name(rng, kind, nouns, used_names),
                    "destination": dest["name"],
                    "star": star,
                    "tags": list(tags) + dest["extra_tags"],
                    "stairs_free": step_free,
                    "list_price_per_night": price,
                    "rooms_available": rng.randint(rmin, rmax),
                    "supplier_id": rng.choice(HOTEL_SUPPLIERS),
                    "lat": round(dest["lat"] + rng.uniform(-0.04, 0.04), 4),
                    "lon": round(dest["lon"] + rng.uniform(-0.04, 0.04), 4),
                }
            )

    while sum(h["stairs_free"] for h in hotels) < 3:  # a step-free choice at every price level
        cheapest = min((h for h in hotels if not h["stairs_free"]), key=lambda h: h["list_price_per_night"])
        cheapest["stairs_free"] = True
    return hotels


def _make_activities(rng: random.Random, dest: dict) -> list[dict]:
    name = dest["name"]
    rows = list(SIGNATURES[name]) + [
        (f"Private Orientation Tour of {name}", "sightseeing", ["family", "quiet"], True, 4, 1800),
        (f"Chef's Table Dinner in {name}", "dining", ["food", "romantic", "quiet"], True, 3, 2800),
    ]

    activities = []
    for title, category, tags, step_free, hours, base in rows:
        activities.append(
            {
                "id": f"A_{dest['code']}_{len(activities) + 1:02d}",
                "name": title,
                "destination": name,
                "category": category,
                "tags": list(tags),
                "stairs_free": step_free,
                "duration_hours": hours,
                "list_price_per_person": _round(base * dest["multiplier"] * rng.uniform(0.95, 1.08), 50),
                "supplier_id": rng.choice(CATEGORY_SUPPLIERS[category]),
            }
        )

    activities.append(
        {
            "id": f"A_{dest['code']}_{len(activities) + 1:02d}",
            "name": f"Airport Transfer, {name}",
            "destination": name,
            "category": "transfer",
            "tags": ["private-car"],
            "stairs_free": True,
            "duration_hours": 2 if name in TRANSFER_PRICE and TRANSFER_PRICE[name] >= 1400 else 1,
            "list_price_per_person": TRANSFER_PRICE.get(name, 800),
            "supplier_id": rng.choice(CATEGORY_SUPPLIERS["transfer"]),
        }
    )
    return activities


def build(seed: int = DEFAULT_SEED) -> dict:
    """Build the whole catalogue in memory. The same seed always gives the same result."""
    missing = {d["name"] for d in DESTINATIONS} - set(SIGNATURES)
    assert not missing, f"No experiences defined for: {missing}"

    rng = random.Random(seed)
    used_names: set[str] = set()
    hotels, activities = [], []
    for dest in DESTINATIONS:
        hotels += _make_hotels(rng, dest, used_names)
        activities += _make_activities(rng, dest)

    return {
        "suppliers": [
            {
                "id": sid, "name": name, "personality": personality, "floor_ratio": ratio,
                "tradeable": tradeable, "patience_rounds": patience, "free_cancellation_days": days,
            }
            for sid, name, personality, ratio, tradeable, patience, days in SUPPLIERS
        ],
        "destinations": [
            {k: d[k] for k in ("name", "code", "region", "kind", "tagline", "lat", "lon", "hub")}
            for d in DESTINATIONS
        ],
        "hotels": hotels,
        "activities": activities,
        "personas": PERSONAS,
    }


def write(out_dir: Path, data: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, rows in data.items():
        text = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
        (out_dir / f"{key}.json").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic travel catalogue.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="folder to write the JSON files to")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default 2026)")
    args = parser.parse_args()

    data = build(args.seed)
    write(args.out, data)
    print(
        f"Wrote {len(data['destinations'])} destinations, {len(data['suppliers'])} suppliers, "
        f"{len(data['hotels'])} hotels and {len(data['activities'])} activities to {args.out}"
    )


if __name__ == "__main__":
    main()