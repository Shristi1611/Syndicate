import json
import re

from pydantic import ValidationError

from app.inventory import DESTINATIONS, HUBS
from app.llm import generate
from app.profile import TravellerProfile, next_question, or_list

FIELDS = {"destination", "origin", "nights", "travellers", "budget_total", "stairs_free", "interests"}

READY = "Great, I have everything I need. Ready to plan your trip!"


def _system() -> str:
    """The extraction prompt. The city lists come from the catalogue, never from a fixed list."""
    cities = ", ".join(f'"{name}"' for name in sorted(DESTINATIONS))
    lines = [
        "Extract trip details from the traveller's message.",
        "Return one JSON object using only these keys, and only the ones the message clearly states:",
        f"- destination: one of {cities}",
    ]
    if HUBS:
        hubs = ", ".join(f'"{name}"' for name in HUBS)
        lines.append(f"- origin: the city the traveller is flying from, one of {hubs}")
    lines += [
        "- nights: whole number",
        "- travellers: whole number of people",
        "- budget_total: whole number of rupees for the whole trip (60k means 60000)",
        "- stairs_free: true if anyone cannot climb stairs or needs step-free access",
        "- interests: list of short lowercase words such as quiet, heritage, food, nightlife",
        "Leave out any key that is not stated. Output the JSON object and nothing else.",
    ]
    return "\n".join(lines)


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
            if value == data["origin"]:
                candidate["origin"] = None    # you cannot fly from where you are going
        elif key == "origin":
            if value not in HUBS or value == data["destination"]:
                continue
            candidate[key] = value
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
    updates = _parse_json(generate(prompt, system=_system())) or {}
    updated = apply_updates(current, updates)
    question = next_question(updated)

    if question is None:
        reply = READY
        if HUBS and not updated.origin:
            reply += (
                " If you would like flights included, tell me which city you are flying from "
                f"({or_list(HUBS)})."
            )
    else:
        reply = question

    return {
        "profile": updated.model_dump(),
        "reply": reply,
        "complete": question is None,
    }