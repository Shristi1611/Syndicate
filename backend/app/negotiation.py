from app.guard import MAX_ROUNDS
from app.inventory import get_item, list_price
from app.llm import generate
from app.supplier_agent import supplier_respond

OPENING_RATIO = 0.75   # first ask: 75% of list price
CONCESSION = 0.4       # each round, move 40% of the way toward the supplier's offer
CLOSE_ENOUGH = 1.03    # accept if the offer is within 3% of our current target
STALL_RATIO = 0.02     # an offer that drops less than 2% of list price counts as stalled


def _traveller_message(item_name: str, target: int, wants: list[str], round_number: int) -> str:
    """The model only words the message. The price comes from code."""
    perks = ", ".join(w.replace("_", " ") for w in wants) or "nothing extra"
    system = (
        "You are a polite, sharp travel agent negotiating for a traveller. "
        "Write one or two short sentences. Plain text only, no markdown."
    )
    prompt = (
        f"Negotiation round {round_number} for '{item_name}'. "
        f"Ask for {target} rupees per unit and request these perks: {perks}. "
        "Mention the target price clearly."
    )
    return generate(prompt, system=system).strip()


def negotiate(item_id: str, wants: list[str] | None = None, max_price: int | None = None) -> dict:
    """Run a negotiation. max_price is the traveller's walk-away price per unit."""
    item = get_item(item_id)
    lp = list_price(item)
    wants = wants or []
    max_price = max_price or lp

    target = round(lp * OPENING_RATIO)
    last_price = lp
    best = None
    log = []
    history = []

    for round_number in range(1, MAX_ROUNDS + 1):
        proposal = _traveller_message(item["name"], target, wants, round_number)
        offer = supplier_respond(item_id, proposal, round_number, history)

        history.append({"role": "traveller", "message": proposal})
        history.append({"role": "supplier", "message": offer["message"]})
        log.append(
            {
                "round": round_number,
                "target": target,
                "traveller": proposal,
                "supplier": offer["message"],
                "price": offer["price"],
                "perks": offer["perks"],
                "fallback": offer["fallback"],
            }
        )

        # Supplier ran out of patience or broke the rules: stop and keep the best earlier offer.
        if offer["fallback"]:
            break

        if best is None or offer["price"] < best["price"]:
            best = offer

        stalled = round_number > 1 and (last_price - offer["price"]) < STALL_RATIO * lp
        close_enough = offer["price"] <= target * CLOSE_ENOUGH
        if offer["price"] <= max_price and (close_enough or stalled):
            break

        last_price = offer["price"]
        target = round(target + (offer["price"] - target) * CONCESSION)

    deal = best if best and best["price"] <= max_price else None
    return {
        "item_id": item_id,
        "item_name": item["name"],
        "list_price": lp,
        "max_price": max_price,
        "deal": deal,
        "saved_per_unit": lp - deal["price"] if deal else 0,
        "rounds": log,
    }