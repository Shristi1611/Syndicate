from pydantic import BaseModel, Field

DESTINATIONS = {"Goa", "Jaipur"}  # matches the cities in our seed data


class TravellerProfile(BaseModel):
    destination: str | None = None
    nights: int | None = Field(default=None, gt=0, le=30)
    travellers: int | None = Field(default=None, gt=0, le=20)
    budget_total: int | None = Field(default=None, gt=0)  # whole trip, in rupees
    stairs_free: bool = False       # needs step-free hotels and activities
    interests: list[str] = Field(default_factory=list)  # e.g. ["quiet", "heritage", "food"]


# Fields we must know before planning, in the order we ask about them.
REQUIRED = ["destination", "nights", "travellers", "budget_total"]

QUESTIONS = {
    "destination": "Which destination would you like, Goa or Jaipur?",
    "nights": "How many nights are you planning to stay?",
    "travellers": "How many people are travelling?",
    "budget_total": "What is your total budget for the trip, in rupees?",
}


def missing_fields(profile: TravellerProfile) -> list[str]:
    """Required fields that are still empty or invalid, in asking order."""
    missing = []
    for name in REQUIRED:
        value = getattr(profile, name)
        if value is None or (name == "destination" and value not in DESTINATIONS):
            missing.append(name)
    return missing


def next_question(profile: TravellerProfile) -> str | None:
    """The one question to ask next, or None when the profile is complete."""
    missing = missing_fields(profile)
    return QUESTIONS[missing[0]] if missing else None