import json
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.bookings import confirm_quote, create_quote, get_booking
from app.chat import chat_turn
from app.config import settings
from app.disruptions import apply_option, propose
from app.inventory import ACTIVITIES, DESTINATIONS, HOTELS, get_item, list_price
from app.llm import status as llm_status
from app.negotiation import negotiate
from app.personas import get_persona, list_personas
from app.planner import plan_trip
from app.postbooking import cancel_confirm, cancel_preview
from app.trip import negotiate_plan, negotiate_plan_events

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


class ProfileRequest(BaseModel):
    profile: dict


class QuoteRequest(BaseModel):
    trip: dict


class ConfirmRequest(BaseModel):
    quote_id: str = Field(min_length=1, max_length=40)


class CancelRequest(BaseModel):
    days_before_trip: int = Field(ge=0, le=365)


class DisruptionRequest(BaseModel):
    event: str = Field(min_length=1, max_length=40)


class ApplyRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=40)
    option_id: str = Field(min_length=1, max_length=60)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_key_configured": bool(settings.llm_api_key),
        "llm_calls": llm_status(),
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


@app.get("/destinations")
def destinations():
    """Every city a trip can be planned for, with its region, tagline and coordinates."""
    return list(DESTINATIONS.values())


@app.get("/hotels")
def hotels(destination: str | None = None):
    """Hotels a traveller can swap to. Public fields only, never floor prices."""
    return [
        {
            "id": h["id"],
            "name": h["name"],
            "destination": h["destination"],
            "star": h["star"],
            "tags": h["tags"],
            "stairs_free": h["stairs_free"],
            "list_price": list_price(h),
        }
        for h in HOTELS.values()
        if destination is None or h["destination"] == destination
    ]


@app.get("/personas")
def personas():
    """Ready-made travellers for the persona switcher."""
    return list_personas()


@app.get("/personas/{persona_id}")
def persona(persona_id: str):
    try:
        return get_persona(persona_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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


@app.post("/plan")
def plan(req: ProfileRequest):
    """Pick hotel, transfer and activities at list prices. No negotiation, no model calls."""
    try:
        return plan_trip(req.profile)
    except ValueError as exc:  # incomplete or invalid profile
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/trip")
def trip(req: ProfileRequest):
    """Plan the trip, negotiate every item, and return the savings."""
    try:
        return negotiate_plan(req.profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/trip/stream")
def trip_stream(req: ProfileRequest, delay: float = Query(default=0, ge=0, le=3)):
    """Same as /trip, but sends each negotiation round to the client as it happens (SSE)."""
    try:
        plan_trip(req.profile)  # validate up front so bad input is a clean 422, not a broken stream
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def events():
        try:
            for event in negotiate_plan_events(req.profile):
                yield f"data: {json.dumps(event)}\n\n"
                if delay:
                    time.sleep(delay)
        except Exception as exc:  # e.g. a setup mistake such as a missing API key
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:200]})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/book/quote")
def book_quote(req: QuoteRequest):
    """Step 1: re-validate prices and stock on the server and hold a quote. Nothing is booked."""
    try:
        return create_quote(req.trip)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/book/confirm")
def book_confirm(req: ConfirmRequest):
    """Step 2: the user's explicit approval. Confirming the same quote twice is safe."""
    try:
        return confirm_quote(req.quote_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/bookings/{booking_id}")
def booking(booking_id: str):
    """Retrieve a booking confirmation and voucher."""
    try:
        return get_booking(booking_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/bookings/{booking_id}/cancel/preview")
def booking_cancel_preview(booking_id: str, req: CancelRequest):
    """Step 1: show what a cancellation would refund. Changes nothing."""
    try:
        return cancel_preview(booking_id, req.days_before_trip)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/bookings/{booking_id}/cancel/confirm")
def booking_cancel_confirm(booking_id: str, req: CancelRequest):
    """Step 2: the user's explicit approval. Cancelling twice is safe."""
    try:
        return cancel_confirm(booking_id, req.days_before_trip)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/bookings/{booking_id}/disruption")
def booking_disruption(booking_id: str, req: DisruptionRequest):
    """Step 1: a disruption happened. Return the options and their cost. Changes nothing."""
    try:
        return propose(booking_id, req.event)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/bookings/{booking_id}/disruption/apply")
def booking_disruption_apply(booking_id: str, req: ApplyRequest):
    """Step 2: the traveller's approval of one option. Applying the same option twice is safe."""
    try:
        return apply_option(booking_id, req.proposal_id, req.option_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))