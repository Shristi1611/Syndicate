from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.chat import chat_turn
from app.config import settings
from app.inventory import ACTIVITIES, HOTELS, get_item, list_price
from app.negotiation import negotiate

app = FastAPI(title="Syndicate", version="0.1.0")

# Lets the React frontend (added later) talk to this server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NegotiateRequest(BaseModel):
    item_id: str
    wants: list[str] = Field(default_factory=list)
    max_price: int | None = Field(default=None, gt=0)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    profile: dict = Field(default_factory=dict)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_key_configured": bool(settings.llm_api_key),
    }


@app.get("/items")
def items():
    """Public catalogue. Floor prices and supplier terms are never exposed."""
    return [
        {
            "id": i["id"],
            "name": i["name"],
            "destination": i["destination"],
            "list_price": list_price(i),
        }
        for i in [*HOTELS.values(), *ACTIVITIES.values()]
    ]


@app.post("/negotiate")
def run_negotiation(req: NegotiateRequest):
    if get_item(req.item_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown item: {req.item_id}")
    return negotiate(req.item_id, req.wants, req.max_price)


@app.post("/chat")
def chat(req: ChatRequest):
    """One conversation turn. Send the profile from the previous reply back each time."""
    try:
        return chat_turn(req.message, req.profile)
    except ValueError as exc:  # profile sent by the client failed validation
        raise HTTPException(status_code=422, detail=str(exc))