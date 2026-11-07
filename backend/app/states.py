"""Which state or union territory each destination is in, and where its marker sits on the globe.

The coordinates are approximate state centres. They only need to be good enough to place a marker.
"""

# State name -> (latitude, longitude) of its marker.
STATES = {
    "Andaman and Nicobar Islands": (11.74, 92.66),
    "Delhi": (28.61, 77.21),
    "Goa": (15.30, 74.12),
    "Himachal Pradesh": (31.10, 77.17),
    "Kerala": (10.85, 76.27),
    "Ladakh": (34.15, 77.58),
    "Maharashtra": (19.75, 75.71),
    "Meghalaya": (25.47, 91.37),
    "Punjab": (31.15, 75.34),
    "Rajasthan": (26.58, 73.84),
    "Uttar Pradesh": (26.85, 80.91),
    "Uttarakhand": (30.07, 79.02),
    "West Bengal": (22.99, 87.85),
}

# Destination name -> the state it is in.
CITY_STATE = {
    "Agra": "Uttar Pradesh",
    "Amritsar": "Punjab",
    "Andaman": "Andaman and Nicobar Islands",
    "Darjeeling": "West Bengal",
    "Delhi": "Delhi",
    "Goa": "Goa",
    "Jaipur": "Rajasthan",
    "Kerala": "Kerala",
    "Kolkata": "West Bengal",
    "Leh": "Ladakh",
    "Manali": "Himachal Pradesh",
    "Meghalaya": "Meghalaya",
    "Mumbai": "Maharashtra",
    "Rishikesh": "Uttarakhand",
    "Udaipur": "Rajasthan",
    "Varanasi": "Uttar Pradesh",
}


def state_of(city: str) -> str | None:
    return CITY_STATE.get(city)


def states_with_cities(destinations: dict[str, dict]) -> list[dict]:
    """Group the catalogue's destinations by state. A state with no destinations is left out,
    and so is a destination we have no state for."""
    grouped: dict[str, list[dict]] = {}
    for name, details in destinations.items():
        state = state_of(name)
        if state is None:
            continue
        grouped.setdefault(state, []).append(
            {"name": name, "region": details.get("region"), "tagline": details.get("tagline")}
        )

    result = []
    for state in sorted(grouped):
        lat, lon = STATES[state]
        result.append(
            {
                "name": state,
                "lat": lat,
                "lon": lon,
                "cities": sorted(grouped[state], key=lambda city: city["name"]),
            }
        )
    return result