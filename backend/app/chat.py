import json
import re

from pydantic import ValidationError

from app.llm import generate
from app.profile import DESTINATIONS, TravellerProfile, next_question

FIELDS = {"destination", "nights", "travellers", "budget_total", "stairs_free", "interests"}

READY = "Great, I have everything I need. Ready to plan your trip!"

SYSTEM = """Extract trip details from the traveller's message.
Return one JSON object using only these keys, and only the ones the message clearly states:
- destination: "Goa" or "Jaipur"
- nights: whole number
- travellers: whole number of people
- budget_total: whole number of rupees for the whole trip (60k means 60000)
- stairs_free: true if anyone cannot climb stairs or needs step-free access
- interests: list of short lowercase words such as quiet, heritage, food, nightlife
Leave out any key that is not stated. Output the JSON object and nothing else."""


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def apply_updates(profile: TravellerProfile, updates: dict) -> TravellerProfile:
    """Merge model-extracted updates into the profile, ignoring anything invalid."""
    data = profile.model_dump()
    for key, value in updates.items():
        if key not in FIELDS:
            continue
        candidate = dict(data)
        if key == "destination":
            if value not in DESTINATIONS:
                continue
            candidate[key] = value
            if value != data["destination"]:
                candidate["hotel_id"] = None  # a swapped hotel belongs to the old destination
        elif key == "interests":
            if not isinstance(value, list):
                continue
            candidate[key] = list(dict.fromkeys(data["interests"] + [str(v).lower() for v in value]))
        elif key == "stairs_free":
            candidate[key] = data[key] or value is True  # once needed, never switched off
        else:
            candidate[key] = value
        try:
            TravellerProfile(**candidate)
        except ValidationError:
            continue
        data = candidate
    return TravellerProfile(**data)


def chat_turn(message: str, profile: dict | None = None) -> dict:
    """One conversation turn: read the message, update the profile, pick the next question."""
    current = TravellerProfile(**(profile or {}))
    prompt = f"Known so far: {current.model_dump_json()}\nTraveller says: {message}"
    updates = _parse_json(generate(prompt, system=SYSTEM)) or {}
    updated = apply_updates(current, updates)
    question = next_question(updated)
    return {
        "profile": updated.model_dump(),
        "reply": question or READY,
        "complete": question is None,
    }