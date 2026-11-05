from dataclasses import dataclass, field

from app.inventory import floor_price, get_item, get_supplier, list_price

MAX_ROUNDS = 4  # hard cap on negotiation rounds, whatever the supplier prefers


@dataclass
class GuardResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def check_offer(
    item_id: str,
    offer: dict,
    round_number: int = 1,
    list_override: int | None = None,
) -> GuardResult:
    """Validate a supplier's offer against its hidden terms.

    offer looks like: {"price": 5600, "perks": ["airport_transfer"]}
    list_override is the list price for the traveller's dates (seasonal pricing). Without it,
    the year-round list price applies.
    """
    item = get_item(item_id)
    if item is None:
        return GuardResult(False, [f"Unknown item: {item_id}"])

    supplier = get_supplier(item["supplier_id"])
    listed = list_override or list_price(item)
    violations = []

    price = offer.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        violations.append("Price must be a positive number")
    else:
        if price < floor_price(item, listed):
            violations.append("Price is below the supplier's floor")
        if price > listed:
            violations.append("Price is above the list price")

    for perk in offer.get("perks", []):
        if perk not in supplier["tradeable"]:
            violations.append(f"Perk not offered by this supplier: {perk}")

    if round_number > MAX_ROUNDS:
        violations.append("Negotiation round limit exceeded")
    if round_number > supplier["patience_rounds"]:
        violations.append("Supplier has run out of patience for this negotiation")

    return GuardResult(ok=not violations, violations=violations)