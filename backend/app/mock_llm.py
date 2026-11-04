"""Free, instant, offline stand-in for a real model.

Used when LLM_PROVIDER=mock, and as the fallback when the live model is down.
"""
import json
import re


def _quoted(pattern: str, system: str) -> list[str]:
    """The quoted names listed after a phrase in the system prompt."""
    match = re.search(pattern, system)
    return re.findall(r'"([^"]+)"', match.group(1)) if match else []


def _extract_trip(prompt: str, system: str) -> str:
    text = prompt.split("Traveller says:", 1)[-1]
    out = {}

    cities = _quoted(r"destination: one of (.+?)\n", system)
    hubs = _quoted(r"origin: .*?one of (.+?)\n", system)

    # "from Delhi" or "Delhi to ..." marks the starting city, so it is not the destination.
    origin = None
    for hub in hubs:
        name = re.escape(hub)
        if re.search(rf"\bfrom\s+{name}\b|\b{name}\s+to\b", text, re.I):
            origin = hub
    if origin:
        out["origin"] = origin

    for city in cities:
        if city != origin and city.lower() in text.lower():
            out["destination"] = city

    m = re.search(r"(\d+)\s*(?:nights?|days?)", text, re.I)
    if m:
        out["nights"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:people|persons|travellers|travelers|adults|of us)", text, re.I)
    if m:
        out["travellers"] = int(m.group(1))
    m = re.search(
        r"(?:₹|\brs\.?\s?)\s*(\d[\d,]*)\s*(k?)|(\d[\d,]*)\s*(k?)\s*(?:rupees|rs\b|budget)",
        text,
        re.I,
    )
    if m:
        num = (m.group(1) or m.group(3)).replace(",", "")
        is_k = (m.group(2) or m.group(4) or "").lower() == "k"
        out["budget_total"] = int(num) * (1000 if is_k else 1)
    if re.search(r"stairs|step-free|wheelchair", text, re.I):
        out["stairs_free"] = True
    out["interests"] = [
        w
        for w in ("quiet", "heritage", "food", "nightlife", "beach", "adventure", "romantic", "luxury")
        if w in text.lower()
    ]
    return json.dumps(out)


def _supplier(prompt: str, system: str) -> str:
    list_price = int(re.search(r"List price: (\d+)", system).group(1))
    floor = int(re.search(r"lowest price is (\d+)", system).group(1))
    perks = re.search(r"willing to give: (.+?)\. Offer", system).group(1).split(", ")
    rnd = int(re.search(r"Negotiation round (\d+)", prompt).group(1))
    price = max(floor, round(list_price * (1 - 0.07 * rnd), -1))
    perk = perks[0]
    message = f"I can do {int(price)} rupees per unit with {perk.replace('_', ' ')} included."
    return (
        '{"message": "' + message + '", "price": ' + str(int(price))
        + ', "perks": ["' + perk + '"]}'
    )


def mock(prompt: str, system: str) -> str:
    if "Extract trip details" in system:  # profile extraction
        return _extract_trip(prompt, system)
    if "Reply with JSON only" in system:  # supplier agent
        return _supplier(prompt, system)
    # traveller agent
    target = re.search(r"Ask for (\d+) rupees", prompt).group(1)
    return f"We would like {target} rupees per unit with the requested perks, please."