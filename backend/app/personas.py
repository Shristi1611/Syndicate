import json

from app.config import ROOT_DIR
from app.profile import TravellerProfile


def _load() -> dict[str, dict]:
    raw = json.loads((ROOT_DIR / "data" / "personas.json").read_text(encoding="utf-8"))
    personas = {}
    for persona in raw:
        # Validated with the same model as live chat, so a bad persona fails at startup.
        profile = TravellerProfile(**persona["profile"]).model_dump()
        personas[persona["id"]] = {**persona, "profile": profile}
    return personas


PERSONAS = _load()


def list_personas() -> list[dict]:
    return list(PERSONAS.values())


def get_persona(persona_id: str) -> dict:
    persona = PERSONAS.get(persona_id)
    if persona is None:
        raise LookupError(f"Unknown persona: {persona_id}")
    return persona