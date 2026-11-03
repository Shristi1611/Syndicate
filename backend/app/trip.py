from app.negotiation import negotiate
from app.planner import plan_trip


def negotiate_plan(profile: dict) -> dict:
    """Plan a trip, then negotiate every line item and total up the savings."""
    plan = plan_trip(profile)

    lines = []
    for item in plan["items"]:
        # Walk-away price is the list price: we never pay more than the plan said.
        result = negotiate(item["item_id"], [], item["unit_price"])
        deal = result["deal"]

        final_unit = deal["price"] if deal else item["unit_price"]
        lines.append(
            {
                **item,
                "final_unit_price": final_unit,
                "final_total": final_unit * item["quantity"],
                "saved": (item["unit_price"] - final_unit) * item["quantity"],
                "perks": deal["perks"] if deal else [],
                "rounds": result["rounds"],
            }
        )

    list_total = plan["list_total"]
    final_total = sum(line["final_total"] for line in lines)
    saved = list_total - final_total

    return {
        "profile": plan["profile"],
        "items": lines,
        "list_total": list_total,
        "final_total": final_total,
        "saved": saved,
        "savings_pct": round(100 * saved / list_total, 1) if list_total else 0,
        "budget": plan["budget"],
        "within_budget": final_total <= plan["budget"],
        "notes": plan["notes"],
    }