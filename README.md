# Syndicate

**Autonomous agents that negotiate your trip.**

Most travel assistants search a catalogue and show you a list. Syndicate sends an
agent to bargain for you.

A traveller agent learns your budget, dates and dealbreakers through conversation,
then negotiates in real time with a network of supplier agents, each with hidden
price floors, perks and cancellation rules. It trades one thing for another and
returns a finished itinerary with the savings it won.

**LLMs negotiate, code enforces.** Language and reasoning come from the models, but
every price and term passes through a deterministic Rules Guard checked against
inventory, so no deal is ever invented. The same guard re-checks every price again
at booking time, so a tampered request is rejected.

**It doesn't stop at booking.** Cancellations, refunds and disruptions (cancelled
flight, overbooked hotel, heavy rain) are handled in two steps: the agent proposes
options with their cost, and nothing changes until the traveller approves one.

Built for the TBO Hackathon, Virtual Travel Agent track.

## How it works

```
 Traveller chat
      |
      v
 Profile (code decides what to ask next; the model only extracts details)
      |
      v
 Planner (code) -- picks hotel, transfer, activities that fit needs and budget
      |
      v
 Negotiation engine -----> Traveller agent  <---- rounds ---->  Supplier agents
      |                    (code sets the                        (LLM, hidden floor
      |                     target price)                         price and perks)
      |                                                                |
      |                                  every offer ---> Rules Guard (code):
      |                                                   no price below floor,
      |                                                   no invented perks,
      |                                                   capped rounds
      v
 Quote  --(traveller approves)-->  Booking  -->  Cancel / disruption options
        (server re-validates                      (preview first, apply only
         prices and stock)                         after approval)
```

Design rules:

- **The model talks, the code decides.** Prices, floors, refunds, stock and totals
  are computed in code. The model never sets a number that is not validated.
- **Never trust the client.** The browser sends choices, not prices. Totals and
  prices are recalculated and re-checked on the server.
- **Ask before consequential actions.** Booking, cancelling and changing a trip
  each need an explicit confirmation step.
- **Safe to retry.** Confirming a quote, cancelling a booking or applying a
  disruption option twice never double-charges or double-books.
- **Know when a human must decide.** Changes the system cannot do safely (for
  example moving a stay that already has extra nights) are refused with a message
  to hand over to a human agent.

## What works today

- Conversation that turns free text into a structured trip profile
- Rule-based planner (stairs-free filter, interests, budget fit)
- Supplier agents with personalities and hidden terms, guarded by the Rules Guard
- Live negotiation of a whole trip, streamed round by round (Server-Sent Events)
- Two-step booking: quote, then confirm, with price and stock validation
- Vouchers and booking retrieval, stored in SQLite
- Two-step cancellation with per-supplier refund windows
- Disruption proposals for overbooked hotel, heavy rain and cancelled flight, and
  applying a chosen option
- Free mock model for testing, so the whole backend runs with no API calls
- Automated tests for the booking, cancellation and disruption flows
- React frontend with a chat and live trip profile (placeholder UI, redesign in progress)

## In progress

- HTTP endpoints for disruption propose and apply
- Live split-screen negotiation view with a savings counter
- Clickable trip map: swap a hotel, add a day or change the route and re-negotiate
- Persona switcher (honeymoon couple, family with a grandmother, solo backpacker)
- Surprise-event buttons on the live screen
- Cached fallback so a slow or rate-limited model never freezes the demo
- Stretch: crowd mode, where each judge plays a traveller and a leaderboard ranks deals

## Project structure

```
syndicate/
  backend/
    app/
      main.py          API endpoints (FastAPI)
      config.py        Settings read from .env
      llm.py           Provider-agnostic model wrapper (Gemini, Claude, mock)
      inventory.py     Loads the seed data, hidden floor prices
      guard.py         Rules Guard: validates every offer in code
      supplier_agent.py  Supplier agent, guarded and retried
      negotiation.py   Traveller-side negotiation loop (streams events)
      profile.py       Trip profile model and missing-field logic
      chat.py          Turns a message into profile updates
      planner.py       Picks hotel, transfer and activities
      trip.py          Negotiates a whole plan and totals the savings
      bookings.py      Quote, confirm, voucher, stock (SQLite)
      postbooking.py   Cancel preview and confirm
      disruptions.py   Disruption proposals and applying an option
    tests/             Automated tests
    requirements.txt
  frontend/            React app (Vite)
  data/                Seed data: suppliers, hotels, activities
  docs/                Planning documents
```

## Setup

You need Python 3.12 or newer and Node.js 20 or newer.

### 1. Configure

Create a file named `.env` in the repo root. It is ignored by git, so your key is
never committed.

```
LLM_PROVIDER=mock
LLM_API_KEY=
LLM_FAST_MODEL=
LLM_STRONG_MODEL=
```

`LLM_PROVIDER` can be:

- `mock`: free and offline. No API calls. Use this for development and tests.
- `gemini`: needs `LLM_API_KEY` and model names. Free tiers have low daily limits.
- `claude`: needs `LLM_API_KEY` and model names.

Switching provider is a config change, not a code change. Model names change often,
so check your provider's current list.

### 2. Run the backend

From the repo root (Windows Command Prompt):

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Mac or Linux, activate with `source .venv/bin/activate`.

Check it at http://127.0.0.1:8000/health, and browse the API at
http://127.0.0.1:8000/docs.

### 3. Run the frontend

In a second terminal:

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### 4. Run the tests

From the `backend` folder with the virtual environment active:

```
python -m pytest -v
```

Tests use a temporary database and force mock mode, so they never touch your real
bookings or your model quota.

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Server status |
| GET | `/items` | Public catalogue (never exposes floor prices) |
| POST | `/chat` | One conversation turn; returns the updated profile and next question |
| POST | `/plan` | Plan a trip at list prices (no model calls) |
| POST | `/trip` | Plan and negotiate every item, return the savings |
| POST | `/trip/stream` | Same, streamed round by round (SSE); `?delay=` slows it for demos |
| POST | `/negotiate` | Negotiate a single item |
| POST | `/book/quote` | Validate a negotiated trip and hold a quote |
| POST | `/book/confirm` | Traveller approval: create the booking |
| GET | `/bookings/{id}` | Booking confirmation and voucher |
| POST | `/bookings/{id}/cancel/preview` | Show the refund; changes nothing |
| POST | `/bookings/{id}/cancel/confirm` | Traveller approval: cancel |

## Assumptions

- **All data is synthetic.** Hotels, activities and suppliers are in `data/`. No real
  customer data and no real payment systems are used.
- **Suppliers are simulated agents**, not real partners. The seed data is shaped like
  a plausible supplier API so it can be swapped for a real one.
- **Availability is total stock**, with no per-date calendar yet.
- **Travel dates are simulated.** Cancellation and disruption demos take a
  `days_before_trip` input instead of real dates.
- **The mock model is only a stand-in.** It concedes on a fixed schedule, so its
  savings are optimistic. Real model runs give different numbers.
- **Prices are in Indian rupees.** One room sleeps up to three people.

## Security notes

- Secrets live in `.env`, which is never committed.
- The public catalogue never exposes floor prices or supplier terms.
- Booking re-validates every price against the Rules Guard on the server, so a
  tampered price is rejected.
- Every API input is validated, and bad input returns a clear 4xx error.

## Built for

TBO Hackathon, Virtual Travel Agent track.