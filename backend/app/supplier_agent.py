import json
import re

from app.guard import check_offer
from app.inventory import floor_price, get_item, get_supplier, list_price
from app.llm import generate

MAX_RETRIES = 2  # extra attempts if the model breaks a rule or returns bad JSON


def _parse_json(text: str) -> dict | None:
    """Pull the first JSON object out of the model's reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _build_system(item: dict, supplier: dict, listed: int) -> str:
    return f"""You are {supplier['name']}, a travel supplier negotiating the price of "{item['name']}".

Your personality: {supplier['personality']}.

Your secret terms (never reveal them):
- List price: {listed} rupees per unit.
- Your absolute lowest price is {floor_price(item, listed)} rupees. Never go below it.
- Perks you are willing to give: {', '.join(supplier['tradeable'])}. Offer only these.
- You lose patience after {supplier['patience_rounds']} rounds, so hold firmer in later rounds.

Negotiate like a real supplier: concede slowly, ask for something in return
(a longer stay, a bigger booking, early payment), and stay in character.
Keep the message to two or three short sentences of plain text, with no markdown or bold.

Reply with JSON only, in this exact shape:
{{"message": "what you say to the traveller", "price": <whole number of rupees per unit>, "perks": ["perk_name"]}}"""


def _build_prompt(proposal: str, round_number: int, history: list[dict]) -> str:
    lines = [f"Negotiation round {round_number}."]
    for turn in history:
        lines.append(f"{turn['role']}: {turn['message']}")
    lines.append(f"traveller: {proposal}")
    lines.append("Make your offer now.")
    return "\n".join(lines)


def supplier_respond(
    item_id: str,
    proposal: str,
    round_number: int,
    history: list[dict] | None = None,
    list_override: int | None = None,
) -> dict:
    """Return the supplier's validated offer: {message, price, perks, fallback}.

    list_override is the list price for the traveller's dates (seasonal pricing)."""
    item = get_item(item_id)
    supplier = get_supplier(item["supplier_id"])
    listed = list_override or list_price(item)
    system = _build_system(item, supplier, listed)
    prompt = _build_prompt(proposal, round_number, history or [])

    feedback = ""
    for _ in range(MAX_RETRIES + 1):
        raw = generate(prompt + feedback, system=system)
        offer = _parse_json(raw)

        if offer is None:
            feedback = "\n\nYour last reply was not valid JSON. Reply with the JSON only."
            continue

        if not isinstance(offer.get("perks"), list):
            offer["perks"] = []

        result = check_offer(item_id, offer, round_number, list_override=listed)
        if result.ok:
            return {**offer, "fallback": False}

        feedback = (
            "\n\nYour last offer was rejected by the rules check: "
            + "; ".join(result.violations)
            + ". Make a corrected offer."
        )

    # The model kept breaking the rules: fall back to a safe list-price offer.
    return {
        "message": "I can offer you our standard rate for this one.",
        "price": listed,
        "perks": [],
        "fallback": True,
    }