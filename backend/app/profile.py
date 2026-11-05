from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.inventory import DESTINATIONS  # every city in the catalogue, read from the data


def or_list(names) -> str:
    """['Delhi', 'Kolkata', 'Mumbai'] becomes 'Delhi, Kolkata or Mumbai'."""
    names = sorted(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + f" or {names[-1]}"


class TravellerProfile(BaseModel):
    destination: str | None = None
    origin: str | None = None       # hub city the flights leave from (optional)
    start_date: str | None = None   # first night, like 2026-12-20 (optional, enables seasonal prices)
    nights: int | None = Field(default=None, gt=0, le=30)
    travellers: int | None = Field(default=None, gt=0, le=20)
    budget_total: int | None = Field(default=None, gt=0)  # whole trip, in rupees
    stairs_free: bool = False       # needs step-free hotels and activities
    interests: list[str] = Field(default_factory=list)  # e.g. ["quiet", "heritage", "food"]
    hotel_id: str | None = None     # set when the traveller picks a specific hotel on the map

    @field_validator("start_date")
    @classmethod
    def _real_date(cls, value):
        if value is None:
            return value
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("start_date must be a real date like 2026-12-20")


# Fields we must know before planning, in the order we ask about them.
REQUIRED = ["destination", "nights", "travellers", "budget_total"]

QUESTIONS = {
    "destination": f"Which destination would you like? I can plan trips to {or_list(DESTINATIONS)}.",
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